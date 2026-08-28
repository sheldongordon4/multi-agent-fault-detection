import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { useStore } from '@app/store';
import {
	DraggableSheet,
	type Detent,
} from '@shared/components/ui/draggable-sheet';
import { useElementHeight } from '@shared/hooks/use-element-height';
import type { TicketSummary } from '@shared/types';
import { FaultTypeChart } from '@features/overview/components/fault-type-chart';
import { LiveSignalChart } from '@features/overview/components/live-signal-chart';
import { StatTiles } from '@features/overview/components/stat-tiles';
import { useFetchSignalBuses } from '@features/overview/hooks/use-fetch-signal-buses';
import { useSignalStream } from '@features/overview/hooks/use-signal-stream';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import { normalizeSeverity } from '../utils/helpers';

/** peek → tiles → everything */
export type DrawerDetent = 0 | 1 | 2;

interface OverviewDrawerProps {
	incidents: TicketSummary[];
	isPending: boolean;
	index: DrawerDetent;
	onIndexChange: (index: DrawerDetent) => void;
	onHeightChange?: (height: number) => void;
}

export function OverviewDrawer({
	incidents,
	isPending,
	index,
	onIndexChange,
	onHeightChange,
}: OverviewDrawerProps) {
	// Both of these are derived from the incidents the page already fetched, so
	// they cost nothing extra — no additional request for the tiles or the chart.
	const counts = useMemo(() => {
		let high = 0;
		let medium = 0;
		let low = 0;
		for (const incident of incidents) {
			const severity = normalizeSeverity(incident.severity);
			if (severity === 'high') high += 1;
			else if (severity === 'medium') medium += 1;
			else low += 1;
		}
		return { total: incidents.length, high, medium, low };
	}, [incidents]);

	// Content is laid out top-to-bottom and clipped from the BOTTOM as the sheet
	// shrinks, so the order here IS the detent order: summary, then tiles, then
	// the charts.
	const [summaryRef, summaryHeight] = useElementHeight<HTMLDivElement>();
	const [tilesRef, tilesHeight] = useElementHeight<HTMLDivElement>();

	// Closed shows nothing but the grabber; the summary rides along with the tiles
	// at half. A full-width bar reading "Grid overview · 0 incidents" was too heavy
	// a resting state for a map-first screen.
	const detents: Detent[] = [
		0,
		summaryHeight + tilesHeight,
		(available) => available,
	];

	const labels = ['Show grid summary', 'Show full overview', 'Collapse overview'];

	// Mid-drag the sheet has a real height but `index` hasn't moved yet — it only
	// changes on release. Styling from `index` alone therefore kept the closed
	// (transparent) surface while the content was already on screen, so tiles
	// appeared to float over the map with nothing behind them. While dragging,
	// always wear the open surface.
	const [dragging, setDragging] = useState(false);
	const handleDraggingChange = useCallback(
		(next: boolean) => setDragging(next),
		[]
	);

	const closed = index === 0 && !dragging;
	const full = index === 2 && !dragging;

	// Rounding tracks how many edges are actually against the viewport:
	//   closed — no surface at all, just the tab
	//   half   — rises from the bottom, so only the top corners are rounded
	//   full   — fills the whole area, so any rounding just leaks the map through
	//            the corners
	const surfaceClass = closed
		? // Closed, the panel keeps its full width (so its content still measures at
			// the right width — a narrow panel would wrap the tiles and corrupt the
			// half-open detent height) and simply goes transparent, leaving the tab.
			// pointer-events-none then matters: an invisible full-width strip would
			// otherwise swallow map clicks along the bottom of the screen.
			'pointer-events-none border-transparent bg-transparent shadow-none backdrop-blur-none'
		: full
			? 'bg-card/95 rounded-none border-0'
			: 'bg-card/95 rounded-b-none border-x-0 border-b-0';

	return (
		<DraggableSheet
			detents={detents}
			index={index}
			onIndexChange={(next) => onIndexChange(next as DrawerDetent)}
			onHeightChange={onHeightChange}
			onDraggingChange={handleDraggingChange}
			label={labels[index]}
			className={surfaceClass}
			grabberClassName={
				closed
					? // A tab flush with the bottom edge rather than a floating pill:
						// trapezoid via clip-path, flat side down, sides flaring outward.
						// No border — clip-path cuts through it and leaves ragged angled
						// edges — so the shape reads from the fill alone.
						'bg-card/90 pointer-events-auto mx-auto w-32 pt-2.5 pb-3 backdrop-blur [clip-path:polygon(0%_100%,14%_0%,86%_0%,100%_100%)]'
					: undefined
			}
		>
			<div ref={summaryRef} className="shrink-0 px-4 pb-3">
				<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
					<span className="flex items-center gap-1.5 font-medium">
						<Activity className="text-muted-foreground size-3.5" />
						Grid overview
					</span>
					<span className="text-muted-foreground">
						<span className="text-foreground font-mono font-medium">
							{counts.total}
						</span>{' '}
						incidents
					</span>
					{counts.high > 0 && (
						<span className="text-destructive font-mono">
							{counts.high} high
						</span>
					)}
					{counts.medium > 0 && (
						<span className="font-mono text-amber-500">
							{counts.medium} medium
						</span>
					)}
				</div>
			</div>

			<div ref={tilesRef} className="shrink-0 px-4 pb-4">
				<StatTiles
					total={counts.total}
					high={counts.high}
					medium={counts.medium}
					low={counts.low}
					isPending={isPending}
				/>
			</div>

			{/* Charts only exist at full height. Mounting them earlier would open a
			    second SSE stream and render two Recharts trees behind a closed
			    drawer, on a page already running a WebGL map and a notification
			    stream. */}
			{index === 2 && (
				<div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
					<div className="space-y-4">
						<LiveSignalSection />
						<FaultTypeChart incidents={incidents} />
					</div>
				</div>
			)}
		</DraggableSheet>
	);
}

/**
 * The live signal chart plus its bus selector.
 *
 * Split into its own component so its SSE subscription is tied to being mounted:
 * hooks can't be called conditionally, so the only way to avoid holding a stream
 * open behind a closed drawer is for the whole section to unmount.
 */
function LiveSignalSection() {
	const selectedBusId = useStore((state) => state.selectedBusId);
	const setSelectedBusId = useStore((state) => state.setSelectedBusId);
	const signalMetric = useStore((state) => state.signalMetric);
	const setSignalMetric = useStore((state) => state.setSignalMetric);

	const { buses, isPending: busesPending } = useFetchSignalBuses();
	const { readings, status } = useSignalStream(selectedBusId);

	// Buses are discovered from live traffic, so the selection has to reconcile
	// with whatever the server reports.
	useEffect(() => {
		if (buses.length === 0) return;
		if (!selectedBusId || !buses.includes(selectedBusId)) {
			setSelectedBusId(buses[0]);
		}
	}, [buses, selectedBusId, setSelectedBusId]);

	return (
		<div className="space-y-2">
			<div className="flex items-center justify-end">
				<Select
					value={selectedBusId ?? ''}
					onValueChange={setSelectedBusId}
					disabled={buses.length === 0}
				>
					<SelectTrigger className="h-8 w-40 text-xs" aria-label="Select bus">
						<SelectValue
							placeholder={busesPending ? 'Loading buses…' : 'No buses live'}
						/>
					</SelectTrigger>
					<SelectContent>
						{buses.map((bus) => (
							<SelectItem key={bus} value={bus} className="font-mono">
								{bus}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</div>

			<LiveSignalChart
				readings={readings}
				status={status}
				metric={signalMetric}
				onMetricChange={setSignalMetric}
				busId={selectedBusId}
			/>
		</div>
	);
}
