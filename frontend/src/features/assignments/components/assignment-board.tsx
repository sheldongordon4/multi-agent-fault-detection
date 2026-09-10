import { useMemo, useState } from 'react';
import {
	DndContext,
	DragOverlay,
	KeyboardSensor,
	PointerSensor,
	closestCorners,
	useDroppable,
	useSensor,
	useSensors,
	type DragEndEvent,
	type DragStartEvent,
} from '@dnd-kit/core';
import { cn } from '@shared/lib/utils';
import type { Assignment, WorkState } from '@shared/types';
import { useNow } from '../hooks/use-now';
import { workStateLabel } from '../utils/helpers';
import { AssignmentCard, DraggableAssignmentCard } from './assignment-card';

/**
 * The five columns an operator actually works in.
 *
 * `closed` is in the enum but not on the board: resolved work ages out after a
 * shift rather than accumulating a sixth column nobody reads. `blocked` is the
 * one that isn't obvious and the one control rooms need most — without it, a
 * transformer held for gas analysis sits in "In progress" for six hours and
 * quietly poisons every cycle-time number the board could produce.
 */
const COLUMNS: WorkState[] = [
	'unassigned',
	'assigned',
	'in_progress',
	'blocked',
	'resolved',
];

const columnDot: Record<string, string> = {
	unassigned: 'bg-muted-foreground/60',
	assigned: 'bg-primary',
	in_progress: 'bg-warning',
	blocked: 'bg-destructive',
	resolved: 'bg-success',
};

function BoardColumn({
	state,
	assignments,
	now,
	onOpen,
	isDragActive,
}: {
	state: WorkState;
	assignments: Assignment[];
	now: number;
	onOpen: (assignment: Assignment) => void;
	isDragActive: boolean;
}) {
	const { setNodeRef, isOver } = useDroppable({ id: state });

	return (
		<section className="flex min-w-0 flex-col gap-2" aria-label={workStateLabel(state)}>
			<header className="flex items-center gap-2 px-1">
				<span className={cn('size-1.5 shrink-0 rounded-full', columnDot[state])} aria-hidden />
				<h3 className="text-muted-foreground font-mono text-[10px] font-medium tracking-wider uppercase">
					{workStateLabel(state)}
				</h3>
				<span className="text-muted-foreground bg-muted ml-auto rounded px-1.5 font-mono text-[10px] tabular-nums">
					{assignments.length}
				</span>
			</header>

			<div
				ref={setNodeRef}
				className={cn(
					'bg-muted/40 border-border/60 flex min-h-[120px] flex-col gap-2 rounded-lg border p-2 transition-colors',
					isOver && 'border-primary bg-primary/5',
					// Only hint at drop targets while something is actually moving.
					isDragActive && !isOver && 'border-dashed'
				)}
			>
				{assignments.map((assignment) => (
					<DraggableAssignmentCard
						key={assignment.incident_id}
						assignment={assignment}
						now={now}
						onOpen={onOpen}
					/>
				))}

				{assignments.length === 0 && (
					<p className="text-muted-foreground/60 px-1 py-3 text-center text-[11px]">
						{isDragActive ? 'Drop here' : 'Nothing here'}
					</p>
				)}
			</div>
		</section>
	);
}

export function AssignmentBoard({
	assignments,
	onChangeState,
	onOpen,
}: {
	assignments: Assignment[];
	onChangeState: (assignment: Assignment, state: WorkState) => void;
	onOpen: (assignment: Assignment) => void;
}) {
	const now = useNow();
	const [dragging, setDragging] = useState<Assignment | null>(null);

	// A pointer has to travel 6px before a drag starts, so clicking a card to
	// open it isn't read as a failed drag. KeyboardSensor is what makes the board
	// usable without a mouse — a control room is not all mice, and the per-card
	// state dropdown in the table view remains the fuller keyboard path.
	const sensors = useSensors(
		useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
		useSensor(KeyboardSensor)
	);

	const byState = useMemo(() => {
		const groups = new Map<WorkState, Assignment[]>(
			COLUMNS.map((state) => [state, [] as Assignment[]])
		);
		for (const assignment of assignments) {
			// `closed` has no column; fold it in with resolved rather than dropping
			// it silently, so the count on screen still matches the query.
			const key = assignment.work_state === 'closed' ? 'resolved' : assignment.work_state;
			groups.get(key)?.push(assignment);
		}
		return groups;
	}, [assignments]);

	const handleDragStart = (event: DragStartEvent) => {
		setDragging((event.active.data.current?.assignment as Assignment) ?? null);
	};

	const handleDragEnd = (event: DragEndEvent) => {
		setDragging(null);

		const assignment = event.active.data.current?.assignment as Assignment | undefined;
		const target = event.over?.id as WorkState | undefined;

		if (!assignment || !target) return;
		if (assignment.work_state === target) return;

		onChangeState(assignment, target);
	};

	return (
		<DndContext
			sensors={sensors}
			collisionDetection={closestCorners}
			onDragStart={handleDragStart}
			onDragEnd={handleDragEnd}
			onDragCancel={() => setDragging(null)}
		>
			<div className="grid h-full grid-cols-[repeat(5,minmax(196px,1fr))] gap-3 overflow-x-auto p-4">
				{COLUMNS.map((state) => (
					<BoardColumn
						key={state}
						state={state}
						assignments={byState.get(state) ?? []}
						now={now}
						onOpen={onOpen}
						isDragActive={dragging !== null}
					/>
				))}
			</div>

			<DragOverlay dropAnimation={null}>
				{dragging && (
					<AssignmentCard
						assignment={dragging}
						now={now}
						onOpen={() => {}}
						isOverlay
					/>
				)}
			</DragOverlay>
		</DndContext>
	);
}
