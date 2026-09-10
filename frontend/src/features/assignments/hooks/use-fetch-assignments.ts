import { useQuery } from '@tanstack/react-query';
import type { AssignmentFilters } from '../store/assignment-slice';
import { assignmentsQueryOptions } from '../utils/query-options';

/**
 * Plain `useQuery`, not suspense: the table renders its own skeleton rows so a
 * refetch after a filter change doesn't blank the whole page.
 */
export const useFetchAssignments = (filters: AssignmentFilters) => {
	const { data, isPending, isFetching, isError, error, refetch } = useQuery({
		...assignmentsQueryOptions(filters),
	});

	return {
		assignments: data?.items ?? [],
		count: data?.count ?? 0,
		isPending,
		isFetching,
		isError,
		error,
		refetch,
	};
};
