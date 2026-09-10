import { cn } from '@shared/lib/utils';
import type { Assignment, Priority, WorkState } from '@shared/types';
import { PRIORITY_LABELS, readSla, workStateLabel } from '../utils/helpers';

/**
 * Work state, not ticket status.
 *
 * `StatusBadge` in features/incidents shows the coordinator's diagnostic status
 * (diagnosed / acknowledged / resolved). This one shows who is doing what about
 * it. Both can be on screen at once and mean different things, so they are
 * deliberately different shapes: status is a plain chip, work state carries a dot.
 */
const stateDot: Record<WorkState, string> = {
	unassigned: 'bg-muted-foreground/60',
	assigned: 'bg-primary',
	in_progress: 'bg-warning',
	blocked: 'bg-destructive',
	resolved: 'bg-success',
	closed: 'bg-muted-foreground/40',
};

export function WorkStateBadge({
	state,
	className,
}: {
	state: WorkState;
	className?: string;
}) {
	return (
		<span
			className={cn(
				'text-muted-foreground inline-flex items-center gap-1.5 text-xs whitespace-nowrap',
				className
			)}
		>
			<span
				className={cn('size-1.5 shrink-0 rounded-full', stateDot[state])}
				aria-hidden
			/>
			{workStateLabel(state)}
		</span>
	);
}

const priorityStyles: Record<Priority, string> = {
	p1: 'border-destructive/40 bg-destructive/10 text-destructive',
	p2: 'border-warning/40 bg-warning/10 text-warning',
	p3: 'border-border bg-muted text-muted-foreground',
	p4: 'border-border bg-muted text-muted-foreground',
};

export function PriorityBadge({
	priority,
	className,
}: {
	priority: Priority;
	className?: string;
}) {
	return (
		<span
			className={cn(
				'inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-medium',
				priorityStyles[priority],
				className
			)}
		>
			{PRIORITY_LABELS[priority]}
		</span>
	);
}

/**
 * Derived SLA readout. Overdue is the only state that gets colour — everything
 * else is quiet, so a red cell on the board means exactly one thing.
 */
export function SlaCell({
	assignment,
	now,
	className,
}: {
	assignment: Assignment;
	/** Passed in so every row on a screen agrees on the time. */
	now?: number;
	className?: string;
}) {
	const { state, label } = readSla(assignment, now);

	const tone =
		state === 'over'
			? 'text-destructive font-medium'
			: state === 'due'
				? 'text-muted-foreground'
				: 'text-muted-foreground/60';

	return (
		<span className={cn('font-mono text-xs tabular-nums', tone, className)}>
			{label}
		</span>
	);
}
