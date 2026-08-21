import { MapPin } from 'lucide-react';
import { Button } from '../../../shared/components/ui/button';
import {
	DraggableSheet,
	type Detent,
} from '../../../shared/components/ui/draggable-sheet';
import { useElementHeight } from '../../../shared/hooks/use-element-height';
import { getBusLocation } from '../../map/utils/bus-locations';
import type { TicketSummary } from '../../../shared/types';
import { IncidentFilters } from './incident-filters';
import { IncidentList } from './incident-list';

interface IncidentListSheetProps {
	incidents: TicketSummary[];
	selectedIncidentId: string | null;
	isPending: boolean;
	isError: boolean;
	onRetry: () => void;
	hasFilters: boolean;
	resultCount: number;
	busFilter: string | null;
	onClearBusFilter: () => void;
	onHoverIncident: (incident: TicketSummary | null) => void;
	collapsed: boolean;
	onCollapsedChange: (collapsed: boolean) => void;
}

/**
 * The incident list as a bottom-anchored sheet: drag or tap the grabber to
 * collapse it down to just search + filters + count.
 *
 * Interaction lives in <DraggableSheet>; this only supplies the two detent
 * heights and the content.
 */
export function IncidentListSheet({
	incidents,
	selectedIncidentId,
	isPending,
	isError,
	onRetry,
	hasFilters,
	resultCount,
	busFilter,
	onClearBusFilter,
	onHoverIncident,
	collapsed,
	onCollapsedChange,
}: IncidentListSheetProps) {
	// Everything above the list is what stays visible when collapsed.
	const [headerRef, headerHeight] = useElementHeight<HTMLDivElement>();

	// Closed = just the header; open = all the space there is.
	const detents: Detent[] = [headerHeight, (available) => available];

	return (
		<DraggableSheet
			detents={detents}
			index={collapsed ? 0 : 1}
			onIndexChange={(next) => onCollapsedChange(next === 0)}
			label={collapsed ? 'Show incident list' : 'Hide incident list'}
		>
			<div ref={headerRef} className="shrink-0">
				<IncidentFilters resultCount={resultCount} />

				{busFilter && (
					<div className="border-border/60 flex items-center gap-2 border-b px-3 py-2">
						<MapPin className="text-muted-foreground size-3.5 shrink-0" />
						<span className="truncate text-xs">
							Filtered to{' '}
							<span className="font-mono font-medium">
								{getBusLocation(busFilter)?.name ?? busFilter}
							</span>
						</span>
						<Button
							variant="ghost"
							size="sm"
							className="ml-auto h-6 px-1.5 text-xs"
							onClick={onClearBusFilter}
						>
							Clear
						</Button>
					</div>
				)}
			</div>

			{/* IncidentList's root is a ScrollArea styled `flex-1`, which only
			    constrains its height inside a flex column. As a plain block it
			    expanded to the full list height and never scrolled. */}
			<div
				className="flex min-h-0 flex-1 flex-col"
				aria-hidden={collapsed}
				inert={collapsed}
			>
				<IncidentList
					incidents={incidents}
					selectedIncidentId={selectedIncidentId}
					isPending={isPending}
					isError={isError}
					onRetry={onRetry}
					hasFilters={hasFilters}
					onHoverIncident={onHoverIncident}
				/>
			</div>
		</DraggableSheet>
	);
}
