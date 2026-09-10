import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { useStore } from '@app/store';
import { Sheet, SheetContent } from '@shared/components/ui/sheet';
import type { Assignment, WorkState } from '@shared/types';
import { ActingAsPicker } from '../components/acting-as-picker';
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
	const isEmpty = ready && assignments.length === 0;

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

				<ActingAsPicker />
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

					{isEmpty && <AssignmentTableEmpty hasFilters={hasFilters} />}

					{ready && assignments.length > 0 && (
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
					// The panel's own header carries the close button and the title, so
					// the sheet must not add a second one — they overlap.
					showCloseButton={false}
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
