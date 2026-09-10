import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router';
import { KanbanSquare, Table2 } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '@app/store';
import { Sheet, SheetContent } from '@shared/components/ui/sheet';
import { ToggleGroup, ToggleGroupItem } from '@shared/components/ui/toggle-group';
import type { Assignment, WorkState } from '@shared/types';
import { ActingAsPicker } from '../components/acting-as-picker';
import { AssignmentBoard } from '../components/assignment-board';
import { AssignmentDetailPanel } from '../components/assignment-detail-panel';
import { AssignmentFilters } from '../components/assignment-filters';
import {
	AssignmentTable,
	AssignmentTableEmpty,
	AssignmentTableError,
	AssignmentTableSkeleton,
} from '../components/assignment-table';
import { useFetchAssignments } from '../hooks/use-fetch-assignments';
import { useFetchOperators } from '../hooks/use-fetch-operators';
import { useUpdateAssignment } from '../hooks/use-update-assignment';
import { impliedWorkState } from '../utils/helpers';

export default function Assignments() {
	// The URL owns which ticket is open, matching how Incidents works — so a
	// ticket is deep-linkable and the back button closes the panel.
	const { incidentId } = useParams<{ incidentId: string }>();
	const navigate = useNavigate();

	const view = useStore((state) => state.assignmentView);
	const setView = useStore((state) => state.setAssignmentView);

	const workState = useStore((state) => state.assignmentWorkState);
	const assignee = useStore((state) => state.assignmentAssignee);
	const severity = useStore((state) => state.assignmentSeverity);
	const priority = useStore((state) => state.assignmentPriority);
	const search = useStore((state) => state.assignmentSearch);

	// One object, used as both the request params and the react-query key, so a
	// filter change can never leave the cache keyed on stale criteria.
	const filters = useMemo(
		() => ({ workState, assignee, severity, priority, search }),
		[workState, assignee, severity, priority, search]
	);

	const { assignments, isPending, isError, refetch } = useFetchAssignments(filters);
	const { operators } = useFetchOperators();
	const { mutate, isPending: isMutating } = useUpdateAssignment(filters);

	const hasFilters =
		workState !== 'all' ||
		assignee !== 'all' ||
		severity !== 'all' ||
		priority !== 'all' ||
		search.trim() !== '';

	const openTicket = (assignment: Assignment) =>
		void navigate(`/assignments/${encodeURIComponent(assignment.incident_id)}`);

	const closeTicket = () => void navigate('/assignments');

	const handleAssign = (assignment: Assignment, operatorId: string | null) => {
		const operator = operators.find((candidate) => candidate.id === operatorId);

		mutate(
			{
				incidentId: assignment.incident_id,
				patch: {
					assignee_id: operatorId,
					expected_version: assignment.version,
				},
				// The server derives the implied state change too; mirroring it here
				// keeps the row from flickering through the old state first.
				optimistic: {
					assignee_id: operatorId,
					assignee_name: operator?.name ?? null,
					assignee_initials: operator?.initials ?? null,
					work_state: impliedWorkState(assignment.work_state, operatorId),
				},
			},
			{
				onSuccess: () =>
					toast.success(
						operator
							? `${assignment.bus_id ?? 'Ticket'} assigned to ${operator.name}`
							: `${assignment.bus_id ?? 'Ticket'} unassigned`
					),
			}
		);
	};

	const handleChangeState = (assignment: Assignment, next: WorkState) => {
		mutate({
			incidentId: assignment.incident_id,
			patch: { work_state: next, expected_version: assignment.version },
			optimistic: { work_state: next },
		});
	};

	const ready = !isPending && !isError;
	// The board keeps its columns even with nothing in them: they ARE the
	// workflow, and a blank page reads as broken rather than as empty. The table
	// has no such structure to show, so it still gets the full empty state.
	const showTableEmpty = ready && view === 'table' && assignments.length === 0;

	return (
		<div className="mx-auto flex h-full w-full max-w-[1600px] flex-col p-4 md:p-6">
			<header className="mb-4 flex flex-wrap items-start justify-between gap-3">
				<div>
					<h1 className="text-xl font-semibold tracking-tight">Assignments</h1>
					<p className="text-muted-foreground mt-1 text-sm">
						Fault tickets and who is working them. Diagnosis stays on the map;
						ownership lives here.
					</p>
				</div>

				<div className="flex items-center gap-3">
					<ToggleGroup
						type="single"
						value={view}
						onValueChange={(next) => next && setView(next as 'board' | 'table')}
						variant="outline"
						size="sm"
					>
						<ToggleGroupItem value="board" aria-label="Board view" className="gap-1.5 text-xs">
							<KanbanSquare className="size-3.5" />
							Board
						</ToggleGroupItem>
						<ToggleGroupItem value="table" aria-label="Table view" className="gap-1.5 text-xs">
							<Table2 className="size-3.5" />
							Table
						</ToggleGroupItem>
					</ToggleGroup>

					<ActingAsPicker />
				</div>
			</header>

			<div className="bg-card border-border/60 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border">
				<AssignmentFilters
					operators={operators}
					resultCount={assignments.length}
					hasFilters={hasFilters}
				/>

				<div className="min-h-0 flex-1 overflow-auto">
					{isPending && <AssignmentTableSkeleton />}

					{!isPending && isError && (
						<AssignmentTableError onRetry={() => void refetch()} />
					)}

					{showTableEmpty && <AssignmentTableEmpty hasFilters={hasFilters} />}

					{ready && view === 'board' && (
						<div className="flex h-full flex-col">
							{assignments.length === 0 && (
								<p className="text-muted-foreground border-border/60 border-b px-4 py-2.5 text-xs">
									{hasFilters
										? 'Nothing matches those filters — the columns below are empty, not missing.'
										: 'No fault tickets yet. They land in Unassigned as soon as the coordinator raises them.'}
								</p>
							)}
							<AssignmentBoard
								assignments={assignments}
								onChangeState={handleChangeState}
								onOpen={openTicket}
							/>
						</div>
					)}

					{ready && view === 'table' && assignments.length > 0 && (
						<AssignmentTable
							assignments={assignments}
							operators={operators}
							onAssign={handleAssign}
							onChangeState={handleChangeState}
							onOpen={openTicket}
							isMutating={isMutating}
						/>
					)}
				</div>
			</div>

			<Sheet
				open={incidentId !== undefined}
				onOpenChange={(open) => !open && closeTicket()}
			>
				<SheetContent
					side="right"
					className="w-full gap-0 p-0 sm:max-w-[440px]"
					// The panel's own header carries the close button and the title.
					aria-describedby={undefined}
				>
					{incidentId !== undefined && (
						<AssignmentDetailPanel
							incidentId={incidentId}
							onClose={closeTicket}
							filters={filters}
						/>
					)}
				</SheetContent>
			</Sheet>
		</div>
	);
}
