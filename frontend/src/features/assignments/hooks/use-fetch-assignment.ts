import { useQuery } from '@tanstack/react-query';
import { assignmentQueryOptions } from '../utils/query-options';

/**
 * One ticket's assignment, fetched independently of any list.
 *
 * The detail panel is opened from two places — the assignments board and the
 * map's incident panel — and only one of them has a list to read from. Fetching
 * by id keeps the panel self-sufficient instead of making the map page load a
 * list it does not otherwise need.
 */
export const useFetchAssignment = (incidentId: string | null) => {
	const { data, isPending, isError, refetch } = useQuery({
		...assignmentQueryOptions(incidentId ?? ''),
		enabled: incidentId !== null,
	});

	return {
		assignment: data ?? null,
		isPending: incidentId !== null && isPending,
		isError,
		refetch,
	};
};
