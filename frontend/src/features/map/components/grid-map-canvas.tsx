import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
	Layer,
	Map as MapLibreMap,
	Marker,
	NavigationControl,
	ScaleControl,
	Source,
	type MapRef,
} from 'react-map-gl/maplibre';
import { useReducedMotion } from 'motion/react';
import { AlertTriangle, Maximize2, Waypoints } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Severity, TicketSummary } from '@shared/types';
import { useResolvedTheme } from '@shared/hooks/use-resolved-theme';
import { cn } from '@shared/lib/utils';
import { getBasemapStyle } from '../utils/basemap';
import { FEEDER_EDGES, getBusLocation } from '../utils/bus-locations';
import {
	deriveBusStatuses,
	deriveParishSeverity,
	formatAge,
	HEALTHY_COLOR,
	recencyWeight,
	SEVERITY_COLOR,
	statusColor,
	type BusStatus,
} from '../utils/grid-status';

// Tight bounding box of the island itself (~ -78.45..-76.1 lng, 17.65..18.6 lat).
const ISLAND_BOUNDS: [[number, number], [number, number]] = [
	[-78.45, 17.65],
	[-76.1, 18.6],
];

// Fence the camera: operators can't pan off to the rest of the Caribbean.
// Deliberately loose — camera padding shifts the centre to dodge the floating
// panels, so the transform needs slack outside the island or MapLibre clamps it
// and you can't zoom out fully. Still clear of Cuba (~19.8°N) and Haiti (~74.5°W).
const JAMAICA_BOUNDS: [number, number, number, number] = [
	-79.4, 16.9, -75.2, 19.3,
];
const MIN_ZOOM = 6.5;
const MAX_ZOOM = 15;

// Below this the bus labels collide (Kingston and Spanish Town are ~17km apart),
// so they're hidden and only the dots remain.
const LABEL_MIN_ZOOM = 8.6;

const PARISHES_URL = '/map/jamaica-parishes.geojson';

const FEEDER_LINE_LAYER = 'feeder-line';

// Static dash pattern — the resting look, and what reduced-motion users keep.
// Hoisted to module scope so its identity is stable: an inline array literal is a
// new object every render, which would make react-map-gl re-apply the paint
// property and fight the animation below.
const FEEDER_DASH: [number, number] = [2, 1.5];

// Phase-shifted dash patterns. MapLibre has no `line-dash-offset`, so "flow" is
// produced by cycling the dash array itself — each entry shifts the gap along the
// line, and stepping through them makes the dashes crawl. Same trick as the
// classic marching-ants example.
const FEEDER_DASH_FLOW: number[][] = [
	[0, 4, 3],
	[0.5, 4, 2.5],
	[1, 4, 2],
	[1.5, 4, 1.5],
	[2, 4, 1],
	[2.5, 4, 0.5],
	[3, 4, 0],
	[0, 0.5, 3, 3.5],
	[0, 1, 3, 3],
	[0, 1.5, 3, 2.5],
	[0, 2, 3, 2],
	[0, 2.5, 3, 1.5],
	[0, 3, 3, 1],
	[0, 3.5, 3, 0.5],
];

// ~14fps. Fast enough to read as flow, slow enough that the map isn't repainting
// at 60fps all shift on a screen that's always up.
const FLOW_FRAME_MS = 70;

export interface GridMapCanvasProps {
	incidents: TicketSummary[];
	activeBusId?: string | null;
	focusedBusId?: string | null;
	hoveredBusId?: string | null;
	onSelectBus?: (busId: string | null) => void;
	padding?: { left: number; right: number; top: number; bottom: number };
}

export function GridMapCanvas({
	incidents,
	activeBusId = null,
	focusedBusId = null,
	hoveredBusId = null,
	onSelectBus,
	padding,
}: GridMapCanvasProps) {
	const theme = useResolvedTheme();
	const mapStyle = useMemo(() => getBasemapStyle(theme), [theme]);
	const mapRef = useRef<MapRef | null>(null);
	const hasFitted = useRef(false);
	const reducedMotion = useReducedMotion();

	const [zoom, setZoom] = useState(8);
	// Layer toggle: the feeder topology is context, not always wanted. Local
	// state — it's a view preference, not something the rest of the app reacts to.
	const [showFeeders, setShowFeeders] = useState(true);
	const [failed, setFailed] = useState(false);
	const [ready, setReady] = useState(false);

	const statuses = useMemo(() => deriveBusStatuses(incidents), [incidents]);
	const parishSeverity = useMemo(
		() => deriveParishSeverity(statuses),
		[statuses]
	);

	// --- live arrival pulse -------------------------------------------------
	// Flash a marker when a NEW ticket lands on it (incidents arrive over SSE).
	const [flashing, setFlashing] = useState<Set<string>>(new Set());
	const seenLatest = useRef<Map<string, string>>(new Map());

	useEffect(() => {
		const arrived: string[] = [];
		for (const s of statuses) {
			if (!s.latestIncidentId) continue;
			const prev = seenLatest.current.get(s.busId);
			// Skip the first observation, or every bus would flash on mount.
			if (prev !== undefined && prev !== s.latestIncidentId) {
				arrived.push(s.busId);
			}
			seenLatest.current.set(s.busId, s.latestIncidentId);
		}
		if (arrived.length === 0 || reducedMotion) return;

		setFlashing((prev) => new Set([...prev, ...arrived]));
		const timer = window.setTimeout(() => {
			setFlashing((prev) => {
				const next = new Set(prev);
				arrived.forEach((id) => next.delete(id));
				return next;
			});
		}, 1600);
		return () => window.clearTimeout(timer);
	}, [statuses, reducedMotion]);

	// --- parish tint + labels ----------------------------------------------
	const parishFillColor = useMemo(() => {
		const entries = Object.entries(parishSeverity);
		if (entries.length === 0) return 'transparent';
		return [
			'match',
			['get', 'parish'],
			...entries.flatMap(([parish, severity]) => [
				parish,
				SEVERITY_COLOR[severity as Severity],
			]),
			'transparent',
		] as unknown as string;
	}, [parishSeverity]);

	// Only label parishes that actually have a fault — labelling all 14 turns the
	// map into a wall of text and buries the thing you're meant to notice.
	const labelledParishes = useMemo(
		() => Object.keys(parishSeverity),
		[parishSeverity]
	);

	// --- feeder topology ----------------------------------------------------
	const feederLines = useMemo(() => {
		const features = FEEDER_EDGES.flatMap(([from, to]) => {
			const a = getBusLocation(from);
			const b = getBusLocation(to);
			if (!a || !b) return [];
			return [
				{
					type: 'Feature' as const,
					properties: { from, to },
					geometry: {
						type: 'LineString' as const,
						coordinates: [
							[a.lng, a.lat],
							[b.lng, b.lat],
						],
					},
				},
			];
		});
		return { type: 'FeatureCollection' as const, features };
	}, []);

	// --- camera -------------------------------------------------------------
	const padKey = padding
		? `${padding.left}-${padding.right}-${padding.top}-${padding.bottom}`
		: 'none';

	useEffect(() => {
		const map = mapRef.current?.getMap();
		if (!map || !padding) return;

		// Camera ops don't need the style loaded, and waiting on `load` is harmful:
		// it fires once per instance, so with `reuseMaps` the listener never fires
		// again and the update is dropped silently.
		map.setPadding(padding, { duration: reducedMotion ? 120 : 300 });

		// fitBounds only on first mount — it recomputes zoom as well as centre, so
		// running it on every padding change would discard the operator's zoom.
		// It must NOT be given `padding` again; setPadding already applied it and
		// the two compound.
		if (!hasFitted.current) {
			hasFitted.current = true;
			map.fitBounds(ISLAND_BOUNDS, { duration: 0 });
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [padKey]);

	// Which substation the camera should look at.
	//
	// Two things can ask for it: selecting an incident (focusedBusId) and clicking
	// a marker to filter (activeBusId). Only the first was honoured, so marker
	// clicks filtered the list but never moved the map. They *used* to appear to
	// zoom, but only as a side effect — expanding the sheet changed the map padding
	// and re-ran fitBounds. That stopped once fitBounds was limited to first mount
	// so it couldn't discard the operator's zoom, taking this with it.
	const cameraTarget = focusedBusId ?? activeBusId;

	// Padding already sits on the transform via setPadding, so easeTo lands the
	// target in the visible strip rather than behind a floating panel.
	useEffect(() => {
		const map = mapRef.current?.getMap();
		if (!map || !cameraTarget) return;
		const site = statuses.find((s) => s.busId === cameraTarget);
		if (!site) return;
		map.easeTo({
			center: [site.lng, site.lat],
			// Zoom in when further out than this, but never pull the operator back
			// out if they're already closer in.
			zoom: Math.max(map.getZoom(), 9.5),
			duration: reducedMotion ? 200 : 600,
		});
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [cameraTarget]);

	// Energise the feeder lines: cycle the dash phase so current appears to flow
	// from the source bus outward.
	//
	// Keyed on `ready` as well as the gates. The previous version depended only on
	// [reducedMotion] and bailed at `if (!map) return` when the ref wasn't
	// populated yet — and since reducedMotion never changes, the effect never ran
	// again and no rAF loop was ever scheduled. (The padding effect survives the
	// same guard only because padKey changes later and gives it a second chance.)
	// `ready` is guaranteed to flip via onLoad/onIdle/onStyleData or the timeout,
	// so this always gets its retry.
	//
	// Gated on reduced motion — a continuous loop is exactly what that preference
	// exists to suppress, so those users keep the static dashed line. rAF also
	// stops on its own in a hidden tab, so a backgrounded console isn't
	// repainting for nothing.
	useEffect(() => {
		if (reducedMotion || !showFeeders) return;
		const map = mapRef.current?.getMap();
		if (!map) return;

		let frame = 0;
		let step = 0;
		let last = 0;

		const tick = (time: number) => {
			frame = requestAnimationFrame(tick);
			if (time - last < FLOW_FRAME_MS) return;
			last = time;
			// The layer only exists once the style and <Layer> have mounted, and it
			// is rebuilt from scratch on a theme swap (setStyle recreates layers).
			if (!map.getLayer(FEEDER_LINE_LAYER)) return;
			step = (step + 1) % FEEDER_DASH_FLOW.length;
			try {
				map.setPaintProperty(
					FEEDER_LINE_LAYER,
					'line-dasharray',
					FEEDER_DASH_FLOW[step]
				);
			} catch {
				// Layer torn down between the check and the set — skip this frame.
			}
		};

		frame = requestAnimationFrame(tick);
		return () => {
			cancelAnimationFrame(frame);
			// Leave the line in its resting pattern rather than mid-phase.
			const m = mapRef.current?.getMap();
			if (m?.getLayer(FEEDER_LINE_LAYER)) {
				try {
					m.setPaintProperty(FEEDER_LINE_LAYER, 'line-dasharray', FEEDER_DASH);
				} catch {
					/* style already gone */
				}
			}
		};
	}, [reducedMotion, ready, showFeeders]);

	// Safety net for the loading hint.
	//
	// None of MapLibre's "I'm ready" signals is dependable across every path here:
	// `load` never fires for a pooled instance under `reuseMaps`; `idle` needs a
	// completed render pass, which a backgrounded tab never performs; `styledata`
	// fires during construction — before React attaches the handler — because the
	// style is a cached singleton object. The events above cover the fast path;
	// this guarantees the overlay can't sit there lying indefinitely. Genuine
	// failures are still reported by onError, which is reliable.
	useEffect(() => {
		const timer = window.setTimeout(() => setReady(true), 3000);
		return () => window.clearTimeout(timer);
	}, []);

	const resetView = useCallback(() => {
		const map = mapRef.current?.getMap();
		if (!map) return;
		map.fitBounds(ISLAND_BOUNDS, { duration: reducedMotion ? 200 : 500 });
	}, [reducedMotion]);

	const handleMarkerClick = useCallback(
		(busId: string) => {
			onSelectBus?.(busId === activeBusId ? null : busId);
		},
		[activeBusId, onSelectBus]
	);

	const showLabels = zoom >= LABEL_MIN_ZOOM;

	return (
		<div className="relative h-full w-full">
			<MapLibreMap
				ref={mapRef}
				reuseMaps
				initialViewState={{
					bounds: ISLAND_BOUNDS,
					fitBoundsOptions: { padding: 16 },
				}}
				mapStyle={mapStyle}
				maxBounds={JAMAICA_BOUNDS}
				minZoom={MIN_ZOOM}
				maxZoom={MAX_ZOOM}
				style={{ width: '100%', height: '100%' }}
				onZoom={(e) => setZoom(e.viewState.zoom)}
				// Three signals, because no single one is reliable:
				//   onLoad     — never fires for a pooled instance under `reuseMaps`
				//   onIdle     — needs a completed render pass, which a backgrounded
				//                tab never performs, so the overlay would stick
				//   onStyleData — style parse/network, independent of both
				// Whichever arrives first clears the overlay.
				onLoad={() => setReady(true)}
				onIdle={() => setReady(true)}
				onStyleData={() => setReady(true)}
				// Clicking bare map clears the bus filter — but marker clicks bubble up
				// to here too, so without this guard selecting a bus was instantly
				// undone by its own click and filtering appeared not to work at all.
				onClick={(e) => {
					const target = e.originalEvent?.target as HTMLElement | null;
					if (target?.closest('.maplibregl-marker')) return;
					onSelectBus?.(null);
				}}
				onError={(e) => {
					const msg = String(e.error?.message ?? e.error);
					// eslint-disable-next-line no-console
					console.error('[GridMap] map error:', msg);
					setFailed(true);
				}}
			>
				<NavigationControl position="bottom-right" showCompass={false} />
				<ScaleControl position="bottom-right" maxWidth={90} unit="metric" />

				<Source id="parishes" type="geojson" data={PARISHES_URL}>
					{/* Faint wash: reads as "this parish has a fault" without fighting
					    the markers for attention. */}
					<Layer
						id="parish-fill"
						type="fill"
						paint={{ 'fill-color': parishFillColor, 'fill-opacity': 0.18 }}
					/>
					<Layer
						id="parish-outline"
						type="line"
						paint={{
							'line-color': parishFillColor,
							'line-opacity': 0.45,
							'line-width': 1,
						}}
					/>
					<Layer
						id="parish-label"
						type="symbol"
						filter={['in', ['get', 'parish'], ['literal', labelledParishes]]}
						layout={{
							'text-field': ['get', 'parish'],
							'text-font': ['Noto Sans Regular'],
							'text-size': 11,
							'text-transform': 'uppercase',
							'text-letter-spacing': 0.08,
						}}
						paint={{
							'text-color': parishFillColor,
							'text-opacity': 0.75,
							'text-halo-color': 'rgba(0,0,0,0.65)',
							'text-halo-width': 1.2,
						}}
					/>
				</Source>

				{/* Feeder topology, drawn under the markers. */}
				{showFeeders && (
				<Source id="feeder" type="geojson" data={feederLines}>
					<Layer
						id="feeder-line"
						type="line"
						layout={{ 'line-cap': 'round', 'line-join': 'round' }}
						paint={{
							'line-color': '#94a3b8',
							'line-opacity': 0.55,
							'line-width': 1.5,
							'line-dasharray': FEEDER_DASH,
						}}
					/>
				</Source>
				)}

				{statuses.map((status) => (
					<Marker
						key={status.busId}
						longitude={status.lng}
						latitude={status.lat}
						anchor="center"
						onClick={() => handleMarkerClick(status.busId)}
					>
						<SubstationPin
							status={status}
							active={status.busId === activeBusId}
							emphasised={
								status.busId === hoveredBusId || status.busId === focusedBusId
							}
							showLabel={showLabels}
							flashing={flashing.has(status.busId)}
							reducedMotion={!!reducedMotion}
						/>
					</Marker>
				))}
			</MapLibreMap>

			{/* Map controls, right-edge rail — the same side and stacking as Zoom
			    Earth, and continuous with MapLibre's own bottom-right group
			    (attribution → zoom → scale). Measured: that group tops out ~145px
			    from the bottom, so 10rem clears it with a small gap and the whole
			    right edge reads as one column of controls. */}
			<div className="absolute right-2.5 bottom-40 z-10 flex flex-col gap-1.5">
				<button
					type="button"
					onClick={() => setShowFeeders((v) => !v)}
					aria-pressed={showFeeders}
					title={showFeeders ? 'Hide feeder lines' : 'Show feeder lines'}
					aria-label={showFeeders ? 'Hide feeder lines' : 'Show feeder lines'}
					className={cn(
						'border-border/60 bg-card/85 hover:bg-accent focus-visible:ring-ring grid size-[29px] place-items-center rounded border shadow backdrop-blur focus-visible:ring-2 focus-visible:outline-none',
						showFeeders ? 'text-foreground' : 'text-muted-foreground/60'
					)}
				>
					<Waypoints className="size-3.5" />
				</button>

				{/* Without this, zooming in has no way back to the island. */}
				<button
					type="button"
					onClick={resetView}
					title="Reset view to Jamaica"
					aria-label="Reset view to Jamaica"
					className="border-border/60 bg-card/85 text-foreground hover:bg-accent focus-visible:ring-ring grid size-[29px] place-items-center rounded border shadow backdrop-blur focus-visible:ring-2 focus-visible:outline-none"
				>
					<Maximize2 className="size-3.5" />
				</button>
			</div>

			<MapLegend />

			{!ready && !failed && (
				<div className="text-muted-foreground pointer-events-none absolute inset-0 grid place-items-center text-xs">
					Loading map…
				</div>
			)}

			{failed && (
				<div className="bg-background/80 absolute inset-0 grid place-items-center p-6 text-center">
					<div className="max-w-xs">
						<AlertTriangle className="text-destructive mx-auto size-5" />
						<p className="mt-2 text-sm font-medium">Map failed to load</p>
						<p className="text-muted-foreground mt-1 text-xs">
							The offline basemap at{' '}
							<code className="font-mono">/map/jamaica.pmtiles</code> could not
							be read. Incident data is unaffected.
						</p>
					</div>
				</div>
			)}
		</div>
	);
}

function MapLegend() {
	const items = [
		{ label: 'High', color: SEVERITY_COLOR.high },
		{ label: 'Medium', color: SEVERITY_COLOR.medium },
		{ label: 'Low', color: SEVERITY_COLOR.low },
		{ label: 'Healthy', color: HEALTHY_COLOR },
	];

	return (
		// Top-centre: the list sheet owns the bottom-left and the detail panel the
		// right, so the horizontal strip along the top is the only spot that stays
		// clear whichever panels are open.
		<div className="border-border/60 bg-card/85 pointer-events-none absolute top-2.5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-md border px-3 py-1.5 shadow backdrop-blur">
			<ul className="flex items-center gap-2.5">
				{items.map((item) => (
					<li
						key={item.label}
						className="text-muted-foreground flex items-center gap-1.5 text-[10px] whitespace-nowrap"
					>
						<span
							className="inline-block size-2 rounded-full"
							style={{ backgroundColor: item.color }}
						/>
						{item.label}
					</li>
				))}
			</ul>
			<span className="bg-border h-3 w-px" aria-hidden />
			<span className="text-muted-foreground/70 text-[10px] whitespace-nowrap">
				Dashed = IEEE13 feeder
			</span>
		</div>
	);
}

function SubstationPin({
	status,
	active,
	emphasised,
	showLabel,
	flashing,
	reducedMotion,
}: {
	status: BusStatus;
	active: boolean;
	emphasised: boolean;
	showLabel: boolean;
	flashing: boolean;
	reducedMotion: boolean;
}) {
	const color = statusColor(status.severity);
	const size = active ? 18 : emphasised ? 16 : 12;
	// Older faults are drawn back; a screen where everything looks equally urgent
	// tells an operator nothing about where to look first.
	const weight = status.severity ? recencyWeight(status.latestAt) : 1;
	const age = formatAge(status.latestAt);

	return (
		<button
			type="button"
			title={`${status.name} · ${status.busId}${
				status.severity
					? ` · ${status.activeCount} active · ${status.severity.toUpperCase()}${age ? ` · ${age}` : ''}`
					: ' · no active incidents'
			}`}
			aria-label={`${status.name} (${status.busId}), ${
				status.severity
					? `${status.activeCount} active, ${status.severity} severity${age ? `, latest ${age}` : ''}`
					: 'no active incidents'
			}`}
			className="focus-visible:ring-ring relative grid cursor-pointer place-items-center rounded-full focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none"
			style={{ width: 34, height: 34 }}
		>
			{/* Sustained pulse for high severity; a brief flash when a new ticket
			    lands. Both suppressed under prefers-reduced-motion — this screen is
			    stared at for a whole shift. */}
			{!reducedMotion && (status.severity === 'high' || flashing) && (
				<span
					className="absolute inline-flex size-7 animate-ping rounded-full opacity-50"
					style={{ backgroundColor: color }}
				/>
			)}

			<span
				className="relative inline-flex items-center justify-center rounded-full border-2 border-white shadow transition-all"
				style={{
					backgroundColor: color,
					width: size,
					height: size,
					opacity: weight,
					outline: active ? `2px solid ${color}` : undefined,
					outlineOffset: 3,
				}}
			/>

			{status.activeCount > 1 && (
				<span
					className="absolute -top-0.5 right-0 grid min-w-4 place-items-center rounded-full border border-white/70 px-1 text-[9px] leading-[13px] font-semibold text-white"
					style={{ backgroundColor: color }}
				>
					{status.activeCount}
				</span>
			)}

			{/* Bus id, not the town name: the basemap already prints the town, and
			    the bus id is what an operator correlates with a ticket. Hidden when
			    zoomed out, where neighbouring labels overlap. */}
			{showLabel && (
				<span className="pointer-events-none absolute top-full mt-0.5 whitespace-nowrap font-mono text-[10px] font-medium text-white/80 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
					{status.busId}
				</span>
			)}
		</button>
	);
}
