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
import { AlertTriangle, Maximize2 } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Severity, TicketSummary } from '@shared/types';
import { SEVERITY_RANK } from '@features/incidents/utils/helpers';
import { useResolvedTheme } from '@shared/hooks/use-resolved-theme';
import { getBasemapStyle } from '../utils/basemap';
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

// Pins closer together than this ON SCREEN merge into one cluster.
//
// Screen distance, not geographic distance, is what makes clustering feel right:
// two buses 17km apart overlap at island zoom and are comfortably separate at
// town zoom, so the same threshold splits clusters apart as you zoom in without
// any per-zoom tuning.
//
// Calibrated, not guessed: at the fitted island view the closest pair (Kingston
// and Spanish Town, ~17km) projects 49px apart, and one zoom step puts them near
// 70px. 64 therefore merges them when the whole island is in frame and splits
// them as soon as you zoom in — which is the behaviour clustering is for.
const CLUSTER_RADIUS_PX = 64;

const PARISHES_URL = '/map/jamaica-parishes.geojson';

// ~14fps. Fast enough to read as flow, slow enough that the map isn't repainting
// at 60fps all shift on a screen that's always up.

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
	// Bumped on every camera move so the screen-space clustering below recomputes.
	// Panning changes projected positions just as much as zooming does, so this
	// cannot key off `zoom` alone.
	const [viewTick, setViewTick] = useState(0);
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

	// --- clustering ---------------------------------------------------------
	// Grouped by distance ON SCREEN rather than on the ground. The whole point of
	// clustering here is overlap: at island zoom Kingston and Spanish Town are the
	// same pixel and must merge; at town zoom they are far apart and must not. A
	// screen-space threshold expresses that directly, and clusters split apart on
	// their own as you zoom in — no per-zoom rules to keep in sync.
	//
	// Deliberately not MapLibre's built-in GeoJSON clustering: that renders through
	// circle layers, which would mean giving up the DOM pins and with them the
	// arrival flash, the severity pulse and the hover/active states. With a handful
	// of monitored buses the cost of doing it here is nil.
	const clusters = useMemo(() => {
		const map = mapRef.current?.getMap();

		// Before the map is up there is nothing to project against, so every bus
		// stands alone; the first camera move re-runs this with real geometry.
		if (!map || !ready) {
			return statuses.map((s) => ({
				key: s.busId,
				lat: s.lat,
				lng: s.lng,
				members: [s],
			}));
		}

		const remaining = [...statuses];
		const groups: {
			key: string;
			lat: number;
			lng: number;
			members: BusStatus[];
		}[] = [];

		while (remaining.length > 0) {
			const seed = remaining.shift()!;
			const members = [seed];
			const seedPoint = map.project([seed.lng, seed.lat]);

			// Walk backwards so splicing does not skip the next candidate.
			for (let i = remaining.length - 1; i >= 0; i -= 1) {
				const candidate = remaining[i];
				const point = map.project([candidate.lng, candidate.lat]);
				const distance = Math.hypot(
					point.x - seedPoint.x,
					point.y - seedPoint.y
				);
				if (distance <= CLUSTER_RADIUS_PX) {
					members.push(candidate);
					remaining.splice(i, 1);
				}
			}

			groups.push({
				// Sorted so the key is stable regardless of which member seeded the
				// group — otherwise React would remount the marker on every pan.
				key: members
					.map((m) => m.busId)
					.sort()
					.join('+'),
				lat: members.reduce((sum, m) => sum + m.lat, 0) / members.length,
				lng: members.reduce((sum, m) => sum + m.lng, 0) / members.length,
				members,
			});
		}

		return groups;
	}, [statuses, ready, zoom, viewTick]);

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

	// Clicking a cluster zooms far enough to break it apart rather than selecting
	// an arbitrary member — the operator asked "what is under here", not "give me
	// one of these".
	const zoomToCluster = useCallback((lng: number, lat: number) => {
		const map = mapRef.current?.getMap();
		if (!map) return;
		map.easeTo({
			center: [lng, lat],
			zoom: Math.min(map.getZoom() + 2, MAX_ZOOM),
			duration: reducedMotion ? 200 : 500,
		});
	}, [reducedMotion]);

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
				onMove={() => setViewTick((v) => v + 1)}
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


				{clusters.map((cluster) => {
					const [only] = cluster.members;

					// One member: the pin behaves exactly as it always has.
					if (cluster.members.length === 1) {
						return (
							<Marker
								key={cluster.key}
								longitude={only.lng}
								latitude={only.lat}
								anchor="center"
								onClick={() => handleMarkerClick(only.busId)}
							>
								<SubstationPin
									status={only}
									active={only.busId === activeBusId}
									emphasised={
										only.busId === hoveredBusId || only.busId === focusedBusId
									}
									showLabel={showLabels}
									flashing={flashing.has(only.busId)}
									reducedMotion={!!reducedMotion}
								/>
							</Marker>
						);
					}

					return (
						<Marker
							key={cluster.key}
							longitude={cluster.lng}
							latitude={cluster.lat}
							anchor="center"
							onClick={() => zoomToCluster(cluster.lng, cluster.lat)}
						>
							<ClusterPin
								members={cluster.members}
								// A cluster containing the selected or hovered bus stays
								// visually connected to the list, so selecting a ticket that
								// happens to be merged does not appear to do nothing.
								active={cluster.members.some((m) => m.busId === activeBusId)}
								emphasised={cluster.members.some(
									(m) => m.busId === hoveredBusId || m.busId === focusedBusId
								)}
								flashing={cluster.members.some((m) => flashing.has(m.busId))}
								reducedMotion={!!reducedMotion}
							/>
						</Marker>
					);
				})}
			</MapLibreMap>

			{/* Map controls, right-edge rail — the same side and stacking as Zoom
			    Earth, and continuous with MapLibre's own bottom-right group
			    (attribution → zoom → scale). Measured: that group tops out ~145px
			    from the bottom, so 10rem clears it with a small gap and the whole
			    right edge reads as one column of controls. */}
			<div className="absolute right-2.5 bottom-40 z-10 flex flex-col gap-1.5">
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
		</div>
	);
}

/**
 * Several buses merged into one pin.
 *
 * Takes the WORST severity of its members, not an average: a cluster hiding one
 * high-severity fault among four healthy buses has to read as high, or clustering
 * would conceal exactly what the map exists to surface. The count is the number
 * of buses merged, and the badge is the number of active incidents across them —
 * two different questions an operator asks.
 */
function ClusterPin({
	members,
	active,
	emphasised,
	flashing,
	reducedMotion,
}: {
	members: BusStatus[];
	active: boolean;
	emphasised: boolean;
	flashing: boolean;
	reducedMotion: boolean;
}) {
	const worst = members.reduce<Severity | null>((acc, m) => {
		if (!m.severity) return acc;
		if (!acc) return m.severity;
		return SEVERITY_RANK[m.severity] > SEVERITY_RANK[acc] ? m.severity : acc;
	}, null);

	const color = statusColor(worst);
	const activeCount = members.reduce((sum, m) => sum + m.activeCount, 0);
	const size = active ? 32 : emphasised ? 30 : 26;

	const names = members.map((m) => m.name).join(', ');

	return (
		<button
			type="button"
			title={`${members.length} sites · ${names}${
				activeCount ? ` · ${activeCount} active` : ' · no active incidents'
			}`}
			aria-label={`Cluster of ${members.length} sites: ${names}. ${
				activeCount ? `${activeCount} active incidents.` : 'No active incidents.'
			} Zoom in to separate them.`}
			className="focus-visible:ring-ring relative grid cursor-pointer place-items-center rounded-full focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none"
			style={{ width: 40, height: 40 }}
		>
			{!reducedMotion && (worst === 'high' || flashing) && (
				<span
					className="absolute inline-flex size-9 animate-ping rounded-full opacity-40"
					style={{ backgroundColor: color }}
				/>
			)}

			<span
				className="relative inline-flex items-center justify-center rounded-full border-2 border-white font-mono font-semibold text-white shadow transition-all"
				style={{
					backgroundColor: color,
					width: size,
					height: size,
					fontSize: size >= 30 ? 12 : 11,
					outline: active ? `2px solid ${color}` : undefined,
					outlineOffset: 3,
				}}
			>
				{members.length}
			</span>
		</button>
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
