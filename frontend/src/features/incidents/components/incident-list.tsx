import { AlertCircle, Inbox, RefreshCw } from 'lucide-react';
import { Link } from 'react-router';
import { cn } from '@shared/lib/utils';
import { Button } from '@shared/components/ui/button';
import {
	Empty,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from '@shared/components/ui/empty';
import { ScrollArea } from '@shared/components/ui/scroll-area';
import { Skeleton } from '@shared/components/ui/skeleton';
import type { TicketSummary } from '@shared/types';
import { formatFaultCode, formatTimestamp } from '../utils/helpers';
import { SeverityBadge } from './severity-badge';

function IncidentRow({
	incident,
	isActive,
	onHover,
}: {
	incident: TicketSummary;
	isActive: boolean;
	onHover?: (incident: TicketSummary | null) => void;
}) {
	return (
		<Link
			to={`/incidents/${encodeURIComponent(incident.incident_id)}`}
			aria-current={isActive ? 'true' : undefined}
			onMouseEnter={() => onHover?.(incident)}
			onMouseLeave={() => onHover?.(null)}
			onFocus={() => onHover?.(incident)}
			onBlur={() => onHover?.(null)}
			className={cn(
				'border-border/50 hover:bg-accent/50 focus-visible:ring-ring block border-b px-3 py-2.5 transition-colors focus-visible:ring-2 focus-visible:outline-none',
				isActive && 'bg-accent'
			)}
		>
			<div className="flex items-start justify-between gap-2">
				<span className="truncate text-sm font-medium">
					{incident.bus_id ?? 'Unknown bus'}
				</span>
				<SeverityBadge severity={incident.severity} showDot={false} />
			</div>

			<div className="text-muted-foreground mt-1 flex items-center gap-2 text-xs">
				<span
					className="font-mono"
					title={incident.fault_type ?? undefined}
				>
					{formatFaultCode(incident.fault_type)}
				</span>
				<span aria-hidden>·</span>
				<span className="truncate font-mono">
					{formatTimestamp(incident.created_at)}
				</span>
			</div>

			{incident.summary && (
				<p className="text-muted-foreground mt-1 line-clamp-1 text-xs">
					{incident.summary}
				</p>
			)}
		</Link>
	);
}

function IncidentListSkeleton() {
	return (
		<div aria-busy="true" aria-label="Loading incidents">
			{Array.from({ length: 8 }).map((_, index) => (
				<div key={index} className="border-border/50 border-b px-3 py-2.5">
					<div className="flex items-center justify-between gap-2">
						<Skeleton className="h-4 w-24" />
						<Skeleton className="h-4 w-12" />
					</div>
					<Skeleton className="mt-2 h-3 w-40" />
					<Skeleton className="mt-1.5 h-3 w-full" />
				</div>
			))}
		</div>
	);
}

interface IncidentListProps {
	incidents: TicketSummary[];
	selectedIncidentId: string | null;
	isPending: boolean;
	isError: boolean;
	onRetry: () => void;
	hasFilters: boolean;
	/** Reports the row under the cursor so the map can highlight its substation. */
	onHoverIncident?: (incident: TicketSummary | null) => void;
}

export function IncidentList({
	incidents,
	selectedIncidentId,
	isPending,
	isError,
	onRetry,
	hasFilters,
	onHoverIncident,
}: IncidentListProps) {
	if (isPending) {
		return (
			<ScrollArea className="min-h-0 flex-1">
				<IncidentListSkeleton />
			</ScrollArea>
		);
	}

	if (isError) {
		return (
			<div className="flex flex-1 items-center justify-center p-6">
				<Empty className="border-none">
					<EmptyHeader>
						<EmptyMedia variant="icon">
							<AlertCircle className="text-destructive" />
						</EmptyMedia>
						<EmptyTitle>Couldn't load incidents</EmptyTitle>
						<EmptyDescription>
							The API on <code className="font-mono">/tickets</code> is
							unreachable. Check that the backend stack is running.
						</EmptyDescription>
					</EmptyHeader>
					<Button variant="outline" size="sm" onClick={onRetry} className="gap-2">
						<RefreshCw className="size-3.5" />
						Try again
					</Button>
				</Empty>
			</div>
		);
	}

	if (incidents.length === 0) {
		return (
			<div className="flex flex-1 items-center justify-center p-6">
				<Empty className="border-none">
					<EmptyHeader>
						<EmptyMedia variant="icon">
							<Inbox className="text-muted-foreground" />
						</EmptyMedia>
						<EmptyTitle>
							{hasFilters ? 'No matching incidents' : 'No incidents yet'}
						</EmptyTitle>
						<EmptyDescription>
							{hasFilters
								? 'No fault tickets match the current filters. Try clearing them.'
								: 'Fault tickets appear here as the coordinator diagnoses detections from the pipeline.'}
						</EmptyDescription>
					</EmptyHeader>
				</Empty>
			</div>
		);
	}

	return (
		<ScrollArea
			className="min-h-0 flex-1"
			onMouseLeave={() => onHoverIncident?.(null)}
		>
			{incidents.map((incident) => (
				<IncidentRow
					key={incident.incident_id}
					incident={incident}
					isActive={incident.incident_id === selectedIncidentId}
					onHover={onHoverIncident}
				/>
			))}
		</ScrollArea>
	);
}
