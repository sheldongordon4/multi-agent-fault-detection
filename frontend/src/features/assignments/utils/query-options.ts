import {
	fetchAssignment,
	fetchAssignmentEvents,
	fetchAssignments,
	fetchOperators,
} from '../services/assignment-service';
import type { AssignmentFilters } from '../store/assignment-slice';
import { assignmentQueryKeys, operatorQueryKeys } from './query-keys';

export const assignmentsQueryOptions = (filters: AssignmentFilters) => ({
	queryKey: assignmentQueryKeys.list(filters),
	queryFn: fetchAssignments,
});

export const assignmentQueryOptions = (incidentId: string) => ({
	queryKey: assignmentQueryKeys.detail(incidentId),
	queryFn: fetchAssignment,
});

// The roster changes far less often than the tickets do, so it is not refetched
// on every window focus the way the assignment list is.
export const operatorsQueryOptions = () => ({
	queryKey: operatorQueryKeys.list(),
	queryFn: fetchOperators,
	staleTime: 5 * 60 * 1000,
});

export const assignmentEventsQueryOptions = (incidentId: string) => ({
	queryKey: assignmentQueryKeys.events(incidentId),
	queryFn: fetchAssignmentEvents,
});
