import { Search, X } from 'lucide-react';
import { Button } from '@shared/components/ui/button';
import { Input } from '@shared/components/ui/input';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectSeparator,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import type { Operator, Priority, Severity, WorkState } from '@shared/types';
import { PRIORITIES, SEVERITIES, WORK_STATES } from '@shared/types';
import { useStore } from '@app/store';
import { PRIORITY_LABELS, workStateLabel } from '../utils/helpers';

const ALL = 'all';
const UNASSIGNED = 'unassigned';

export function AssignmentFilters({
	operators,
	resultCount,
	hasFilters,
}: {
	operators: Operator[];
	resultCount: number;
	hasFilters: boolean;
}) {
	const search = useStore((state) => state.assignmentSearch);
	const workState = useStore((state) => state.assignmentWorkState);
	const assignee = useStore((state) => state.assignmentAssignee);
	const severity = useStore((state) => state.assignmentSeverity);
	const priority = useStore((state) => state.assignmentPriority);

	const setSearch = useStore((state) => state.setAssignmentSearch);
	const setWorkState = useStore((state) => state.setAssignmentWorkState);
	const setAssignee = useStore((state) => state.setAssignmentAssignee);
	const setSeverity = useStore((state) => state.setAssignmentSeverity);
	const setPriority = useStore((state) => state.setAssignmentPriority);
	const reset = useStore((state) => state.resetAssignmentFilters);

	return (
		<div className="border-border/60 flex flex-wrap items-center gap-2 border-b px-4 py-3">
			<div className="relative min-w-[200px] flex-1 sm:max-w-xs">
				<Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
				<Input
					value={search}
					onChange={(event) => setSearch(event.target.value)}
					placeholder="Search bus, fault, ticket…"
					className="h-8 pl-8 text-xs"
					aria-label="Search assignments"
				/>
			</div>

			<Select
				value={workState}
				onValueChange={(value) => setWorkState(value as WorkState | 'all')}
			>
				<SelectTrigger className="h-8 w-[140px] text-xs" aria-label="Filter by state">
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value={ALL}>All states</SelectItem>
					<SelectSeparator />
					{WORK_STATES.map((state) => (
						<SelectItem key={state} value={state}>
							{workStateLabel(state)}
						</SelectItem>
					))}
				</SelectContent>
			</Select>

			<Select value={assignee} onValueChange={setAssignee}>
				<SelectTrigger className="h-8 w-[160px] text-xs" aria-label="Filter by assignee">
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value={ALL}>Anyone</SelectItem>
					<SelectItem value={UNASSIGNED}>Unassigned only</SelectItem>
					<SelectSeparator />
					{operators.map((operator) => (
						<SelectItem key={operator.id} value={operator.id}>
							{operator.name}
						</SelectItem>
					))}
				</SelectContent>
			</Select>

			<Select
				value={severity}
				onValueChange={(value) => setSeverity(value as Severity | 'all')}
			>
				<SelectTrigger className="h-8 w-[130px] text-xs" aria-label="Filter by severity">
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value={ALL}>Any severity</SelectItem>
					<SelectSeparator />
					{[...SEVERITIES].reverse().map((level) => (
						<SelectItem key={level} value={level} className="capitalize">
							{level}
						</SelectItem>
					))}
				</SelectContent>
			</Select>

			<Select
				value={priority}
				onValueChange={(value) => setPriority(value as Priority | 'all')}
			>
				<SelectTrigger className="h-8 w-[120px] text-xs" aria-label="Filter by priority">
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value={ALL}>Any priority</SelectItem>
					<SelectSeparator />
					{PRIORITIES.map((level) => (
						<SelectItem key={level} value={level}>
							{PRIORITY_LABELS[level]}
						</SelectItem>
					))}
				</SelectContent>
			</Select>

			{hasFilters && (
				<Button
					variant="ghost"
					size="sm"
					onClick={reset}
					className="h-8 gap-1.5 text-xs"
				>
					<X className="size-3.5" />
					Clear
				</Button>
			)}

			<span className="text-muted-foreground ml-auto font-mono text-xs tabular-nums">
				{resultCount} {resultCount === 1 ? 'ticket' : 'tickets'}
			</span>
		</div>
	);
}
