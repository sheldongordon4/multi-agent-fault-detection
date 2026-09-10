import { useDraggable } from '@dnd-kit/core';
import { GripVertical } from 'lucide-react';
import { cn } from '@shared/lib/utils';
import type { Assignment } from '@shared/types';
import { formatFaultCode } from '@features/incidents/utils/helpers';
import { normalizeSeverity } from '@features/incidents/utils/helpers';
import { formatAge } from '../utils/helpers';
import { PriorityBadge, SlaCell } from './assignment-badges';
import { OperatorAvatar, UnassignedAvatar } from './operator-avatar';

/**
 * Severity as a stripe on the leading edge rather than a badge: a column of red
 * has to read before any of the text does.
 */
const severityStripe: Record<string, string> = {
	high: 'bg-destructive',
	medium: 'bg-warning',
	low: 'bg-success',
};

export function AssignmentCard({
	assignment,
	now,
	onOpen,
	isDragging = false,
	isOverlay = false,
}: {
	assignment: Assignment;
	now: number;
	onOpen: (assignment: Assignment) => void;
	isDragging?: boolean;
	/** True for the copy that follows the cursor, which must not be interactive. */
	isOverlay?: boolean;
}) {
	const severity = normalizeSeverity(assignment.severity);

	return (
		<article
			className={cn(
				'group/card bg-card border-border/60 relative rounded-lg border py-2 pr-2 pl-3 shadow-xs transition-shadow',
				isDragging && 'opacity-40',
				isOverlay && 'rotate-[-1.5deg] shadow-lg'
			)}
		>
			<span
				className={cn(
					'absolute inset-y-0 left-0 w-[3px] rounded-l-lg',
					severityStripe[severity]
				)}
				aria-hidden
			/>

			<button
				type="button"
				onClick={() => onOpen(assignment)}
				className="w-full cursor-pointer text-left focus-visible:outline-none"
				aria-label={`Open ${assignment.bus_id ?? assignment.incident_id}`}
				tabIndex={isOverlay ? -1 : 0}
			>
				<div className="flex items-center gap-2">
					<span className="font-mono text-xs font-medium">
						{assignment.bus_id ?? '—'}
					</span>
					<span className="text-muted-foreground border-border/60 rounded border px-1 font-mono text-[10px]">
						{formatFaultCode(assignment.fault_type)}
					</span>
					<PriorityBadge priority={assignment.priority} className="ml-auto" />
				</div>

				{assignment.summary && (
					<p className="text-muted-foreground mt-1.5 line-clamp-2 text-[11px] leading-snug">
						{assignment.summary}
					</p>
				)}

				<div className="mt-2 flex items-center gap-2">
					{assignment.assignee_id ? (
						<OperatorAvatar
							operatorId={assignment.assignee_id}
							name={assignment.assignee_name}
							initials={assignment.assignee_initials}
						/>
					) : (
						<UnassignedAvatar />
					)}
					<span className="text-muted-foreground truncate text-[11px]">
						{assignment.assignee_name ?? 'Unassigned'}
					</span>
					<span className="text-muted-foreground/70 ml-auto shrink-0 font-mono text-[10px] tabular-nums">
						{formatAge(assignment.created_at, now)}
					</span>
				</div>

				<div className="mt-1 flex justify-end">
					<SlaCell assignment={assignment} now={now} className="text-[10px]" />
				</div>
			</button>
		</article>
	);
}

/**
 * The card as it appears on the board — draggable.
 *
 * The drag handle is a separate control rather than the whole card, so the card
 * body stays a plain button that opens the detail panel. Making the whole card
 * draggable would swallow the click.
 */
export function DraggableAssignmentCard({
	assignment,
	now,
	onOpen,
}: {
	assignment: Assignment;
	now: number;
	onOpen: (assignment: Assignment) => void;
}) {
	const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
		id: assignment.incident_id,
		data: { assignment },
	});

	return (
		<div ref={setNodeRef} className="relative">
			<AssignmentCard assignment={assignment} now={now} onOpen={onOpen} isDragging={isDragging} />

			<button
				type="button"
				className={cn(
					'text-muted-foreground/50 hover:text-foreground absolute top-1.5 right-1.5 cursor-grab rounded p-0.5',
					'opacity-0 transition-opacity group-hover/card:opacity-100 focus-visible:opacity-100',
					'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none'
				)}
				aria-label={`Move ${assignment.bus_id ?? assignment.incident_id} to another column`}
				{...attributes}
				{...listeners}
			>
				<GripVertical className="size-3.5" />
			</button>
		</div>
	);
}
