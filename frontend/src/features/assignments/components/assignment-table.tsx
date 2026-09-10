import { AlertCircle, ClipboardList, ExternalLink, RefreshCw } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '@shared/components/ui/button';
import {
	Empty,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from '@shared/components/ui/empty';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import { Skeleton } from '@shared/components/ui/skeleton';
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@shared/components/ui/table';
import { SeverityBadge } from '@features/incidents/components/severity-badge';
import { formatFaultCode } from '@features/incidents/utils/helpers';
import type { Assignment, Operator, WorkState } from '@shared/types';
import { WORK_STATES } from '@shared/types';
import { useNow } from '../hooks/use-now';
import { formatAge, workStateLabel } from '../utils/helpers';
import { AssigneePicker } from './assignee-picker';
import { PriorityBadge, SlaCell } from './assignment-badges';

const COLUMN_COUNT = 8;

export function AssignmentTableSkeleton({ rows = 6 }: { rows?: number }) {
	return (
		<Table>
			<TableBody>
				{Array.from({ length: rows }).map((_, index) => (
					<TableRow key={index}>
						<TableCell colSpan={COLUMN_COUNT} className="p-2">
							<Skeleton className="h-8 w-full" />
						</TableCell>
					</TableRow>
				))}
			</TableBody>
		</Table>
	);
}

export function AssignmentTableError({ onRetry }: { onRetry: () => void }) {
	return (
		<div className="flex h-full items-center justify-center p-8">
			<Empty className="border-none">
				<EmptyHeader>
					<EmptyMedia variant="icon">
						<AlertCircle className="text-destructive" />
					</EmptyMedia>
					<EmptyTitle>Couldn't load assignments</EmptyTitle>
					<EmptyDescription>
						The API is unreachable, or no fault tickets exist yet.
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

export function AssignmentTableEmpty({ hasFilters }: { hasFilters: boolean }) {
	return (
		<div className="flex h-full items-center justify-center p-8">
			<Empty className="border-none">
				<EmptyHeader>
					<EmptyMedia variant="icon">
						<ClipboardList className="text-muted-foreground" />
					</EmptyMedia>
					<EmptyTitle>
						{hasFilters ? 'Nothing matches those filters' : 'No fault tickets yet'}
					</EmptyTitle>
					<EmptyDescription>
						{hasFilters
							? 'Clear a filter to widen the search.'
							: 'Tickets appear here as soon as the coordinator raises them.'}
					</EmptyDescription>
				</EmptyHeader>
			</Empty>
		</div>
	);
}

export function AssignmentTable({
	assignments,
	operators,
	onAssign,
	onChangeState,
	onOpen,
	isMutating,
}: {
	assignments: Assignment[];
	operators: Operator[];
	onAssign: (assignment: Assignment, operatorId: string | null) => void;
	onChangeState: (assignment: Assignment, state: WorkState) => void;
	onOpen: (assignment: Assignment) => void;
	isMutating: boolean;
}) {
	// Age and SLA are derived from the wall clock, so the table needs a heartbeat
	// of its own — a refetch is not guaranteed on an idle board.
	const now = useNow();

	return (
		<Table>
			<TableHeader>
				<TableRow className="hover:bg-transparent">
					<TableHead className="text-muted-foreground w-[92px] px-3 text-[11px] font-medium tracking-wide uppercase">
						Severity
					</TableHead>
					<TableHead className="text-muted-foreground px-3 text-[11px] font-medium tracking-wide uppercase">
						Bus
					</TableHead>
					<TableHead className="text-muted-foreground px-3 text-[11px] font-medium tracking-wide uppercase">
						Fault
					</TableHead>
					<TableHead className="text-muted-foreground w-[56px] px-3 text-[11px] font-medium tracking-wide uppercase">
						Pri
					</TableHead>
					<TableHead className="text-muted-foreground w-[168px] px-3 text-[11px] font-medium tracking-wide uppercase">
						State
					</TableHead>
					<TableHead className="text-muted-foreground w-[212px] px-3 text-[11px] font-medium tracking-wide uppercase">
						Assignee
					</TableHead>
					<TableHead className="text-muted-foreground w-[72px] px-3 text-right text-[11px] font-medium tracking-wide uppercase">
						Age
					</TableHead>
					<TableHead className="text-muted-foreground w-[96px] px-3 text-right text-[11px] font-medium tracking-wide uppercase">
						SLA
					</TableHead>
				</TableRow>
			</TableHeader>

			<TableBody>
				{assignments.map((assignment) => (
					<TableRow key={assignment.incident_id} className="group">
						<TableCell className="px-3">
							<SeverityBadge severity={assignment.severity} showDot={false} />
						</TableCell>

						<TableCell className="px-3">
							<div className="flex items-center gap-1.5">
								<button
									type="button"
									onClick={() => onOpen(assignment)}
									className="hover:text-primary cursor-pointer font-mono text-sm font-medium underline-offset-2 hover:underline"
								>
									{assignment.bus_id ?? '—'}
								</button>
								{/* The map is still the map — this is the way back to it. */}
								<Link
									to={`/incidents/${encodeURIComponent(assignment.incident_id)}`}
									className="text-muted-foreground hover:text-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
									aria-label={`View ${assignment.bus_id ?? assignment.incident_id} on the map`}
									title="View on map"
								>
									<ExternalLink className="size-3.5" />
								</Link>
							</div>
						</TableCell>

						<TableCell className="text-muted-foreground max-w-[280px] truncate px-3 font-mono text-xs">
							<span title={assignment.fault_type ?? undefined}>
								{formatFaultCode(assignment.fault_type)}
							</span>
						</TableCell>

						<TableCell className="px-3">
							<PriorityBadge priority={assignment.priority} />
						</TableCell>

						<TableCell className="px-3">
							<Select
								value={assignment.work_state}
								onValueChange={(next) =>
									onChangeState(assignment, next as WorkState)
								}
								disabled={isMutating}
							>
								<SelectTrigger
									className="h-8 w-full text-xs"
									aria-label={`Work state for ${assignment.bus_id ?? assignment.incident_id}`}
								>
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									{WORK_STATES.map((state) => (
										<SelectItem key={state} value={state}>
											{workStateLabel(state)}
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</TableCell>

						<TableCell className="px-3">
							<AssigneePicker
								value={assignment.assignee_id}
								operators={operators}
								fallbackName={assignment.assignee_name}
								fallbackInitials={assignment.assignee_initials}
								onChange={(operatorId) => onAssign(assignment, operatorId)}
								disabled={isMutating}
								aria-label={`Assignee for ${assignment.bus_id ?? assignment.incident_id}`}
							/>
						</TableCell>

						<TableCell className="text-muted-foreground px-3 text-right font-mono text-xs tabular-nums">
							{formatAge(assignment.created_at)}
						</TableCell>

						<TableCell className="px-3 text-right">
							<SlaCell assignment={assignment} now={now} />
						</TableCell>
					</TableRow>
				))}
			</TableBody>
		</Table>
	);
}
