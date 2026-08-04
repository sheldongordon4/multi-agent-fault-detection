import { Search, X } from 'lucide-react';
import { useStore } from '../../../app/store';
import { Button } from '../../../shared/components/ui/button';
import { Input } from '../../../shared/components/ui/input';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '../../../shared/components/ui/select';
import { SEVERITIES, TICKET_STATUSES } from '../../../shared/types';
import type { SeverityFilter, StatusFilter } from '../store/incident-slice';

export function IncidentFilters({ resultCount }: { resultCount: number }) {
	const search = useStore((state) => state.incidentSearch);
	const severity = useStore((state) => state.incidentSeverity);
	const status = useStore((state) => state.incidentStatus);
	const setSearch = useStore((state) => state.setIncidentSearch);
	const setSeverity = useStore((state) => state.setIncidentSeverity);
	const setStatus = useStore((state) => state.setIncidentStatus);
	const reset = useStore((state) => state.resetIncidentFilters);

	const isFiltered =
		search.trim() !== '' || severity !== 'all' || status !== 'all';

	return (
		<div className="border-border/60 flex flex-col gap-2 border-b p-3">
			<div className="relative">
				<Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
				<Input
					value={search}
					onChange={(event) => setSearch(event.target.value)}
					placeholder="Search bus, fault type, incident…"
					aria-label="Search incidents"
					className="h-9 pl-8"
				/>
			</div>

			<div className="flex items-center gap-2">
				<Select
					value={severity}
					onValueChange={(value) => setSeverity(value as SeverityFilter)}
				>
					<SelectTrigger className="h-8 flex-1 text-xs" aria-label="Filter by severity">
						<SelectValue placeholder="Severity" />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="all">All severities</SelectItem>
						{SEVERITIES.map((value) => (
							<SelectItem key={value} value={value} className="capitalize">
								{value}
							</SelectItem>
						))}
					</SelectContent>
				</Select>

				<Select
					value={status}
					onValueChange={(value) => setStatus(value as StatusFilter)}
				>
					<SelectTrigger className="h-8 flex-1 text-xs" aria-label="Filter by status">
						<SelectValue placeholder="Status" />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="all">All statuses</SelectItem>
						{TICKET_STATUSES.map((value) => (
							<SelectItem key={value} value={value} className="capitalize">
								{value}
							</SelectItem>
						))}
					</SelectContent>
				</Select>

				{isFiltered && (
					<Button
						variant="ghost"
						size="icon"
						className="size-8 shrink-0"
						onClick={reset}
						aria-label="Clear filters"
					>
						<X className="size-4" />
					</Button>
				)}
			</div>

			<p className="text-muted-foreground font-mono text-[11px]">
				{resultCount} {resultCount === 1 ? 'incident' : 'incidents'}
			</p>
		</div>
	);
}
