import { Link } from 'react-router';
import { History, Repeat2 } from 'lucide-react';
import { Badge } from '@shared/components/ui/badge';
import { Skeleton } from '@shared/components/ui/skeleton';
import type { RepeatOffender } from '@shared/types';
import { faultTypeInfo, normalizeSeverity } from '@features/incidents/utils/helpers';
import { useFetchRepeatOffenders } from '../hooks/use-fetch-repeat-offenders';
import { offenderSubtitle } from '../utils/helpers';

/**
 * Buses that keep faulting the same way.
 *
 * The one view here that is predictive rather than reactive. Everything else on
 * this page answers "what just happened"; this answers "what is about to", and
 * it does it from ticket rows that were already in Postgres — a repeated
 * transient at one location is what SOP-SLG-005 describes as the precursor to a
 * permanent failure.
 */

const severityTone: Record<string, string> = {
	high: 'border-destructive/40 text-destructive',
	medium: 'border-warning/40 text-warning',
	low: 'border-border text-muted-foreground',
};

function OffenderRow({ offender }: { offender: RepeatOffender }) {
	const info = faultTypeInfo(offender.fault_code);
	const severity = normalizeSeverity(offender.worst_severity);
	const latest = offender.recent_incident_ids[0];

	const row = (
		<div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
			<div className="min-w-0">
				<div className="flex flex-wrap items-center gap-2">
					<span className="font-mono text-sm font-medium">{offender.bus_id}</span>
					<Badge
						variant="outline"
						className={`h-5 px-1.5 text-[11px] ${severityTone[severity] ?? severityTone.low}`}
					>
						{offender.fault_code}
					</Badge>
					<span className="text-muted-foreground truncate text-xs">
						{info.name}
					</span>
				</div>

				<p className="text-muted-foreground mt-1 text-xs">
					{offenderSubtitle(offender)}
				</p>
			</div>

			<div className="flex items-baseline gap-1.5">
				<span className="font-mono text-2xl leading-none font-semibold tabular-nums">
					{offender.occurrences}
				</span>
				<span className="text-muted-foreground text-xs">times</span>
			</div>
		</div>
	);

	// The whole row links to the most recent occurrence, which is where an
	// operator goes to see what happened last time.
	return (
		<li className="border-border/60 hover:bg-muted/40 rounded-md border p-3 transition-colors">
			{latest ? (
				<Link to={`/incidents/${encodeURIComponent(latest)}`} className="block">
					{row}
				</Link>
			) : (
				row
			)}
		</li>
	);
}

export function RepeatOffendersCard({ limit = 5 }: { limit?: number }) {
	const { offenders, windowDays, isPending, isError } = useFetchRepeatOffenders();

	return (
		<section className="border-border/60 bg-card rounded-lg border">
			<header className="border-border/60 flex items-center justify-between border-b px-4 py-3">
				<div className="flex items-center gap-2">
					<Repeat2 className="text-primary size-4" />
					<h2 className="text-sm font-medium">Repeat offenders</h2>
				</div>
				<span className="text-muted-foreground text-xs">last {windowDays} days</span>
			</header>

			<div className="p-4">
				{isPending && (
					<div className="space-y-2">
						<Skeleton className="h-16 w-full" />
						<Skeleton className="h-16 w-full" />
					</div>
				)}

				{!isPending && isError && (
					<p className="text-muted-foreground text-sm">
						Could not load recurrence history.
					</p>
				)}

				{!isPending && !isError && offenders.length === 0 && (
					<div className="text-muted-foreground flex items-center gap-2 text-sm">
						<History className="size-4 shrink-0" />
						<span>
							No bus has faulted the same way twice in the last {windowDays} days.
						</span>
					</div>
				)}

				{!isPending && !isError && offenders.length > 0 && (
					<ul className="space-y-2">
						{offenders.slice(0, limit).map((offender) => (
							<OffenderRow
								key={`${offender.bus_id}:${offender.fault_code}`}
								offender={offender}
							/>
						))}
					</ul>
				)}
			</div>
		</section>
	);
}
