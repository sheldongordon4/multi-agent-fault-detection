import { useQuery } from '@tanstack/react-query';
import { assignmentEventsQueryOptions } from '../utils/query-options';

export const useFetchAssignmentEvents = (incidentId: string | null) => {
	const { data, isPending, isError, refetch } = useQuery({
		...assignmentEventsQueryOptions(incidentId ?? ''),
		enabled: incidentId !== null,
	});

	return {
		events: data?.items ?? [],
		isPending: incidentId !== null && isPending,
		isError,
		refetch,
	};
};
