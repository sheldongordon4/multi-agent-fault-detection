import { useQuery } from '@tanstack/react-query';
import {
	DEFAULT_INCIDENT_LIMIT,
	incidentsQueryOptions,
} from '../utils/query-options';

/**
 * Plain `useQuery` (not suspense): the list renders its own skeleton inside the
 * master-detail layout, so a pending fetch must not suspend the whole page.
 */
export const useFetchIncidents = (limit: number = DEFAULT_INCIDENT_LIMIT) => {
	const { data, isPending, isError, error, refetch, isFetching } = useQuery({
		...incidentsQueryOptions(limit),
	});

	return {
		incidents: data?.items ?? [],
		count: data?.count ?? 0,
		isPending,
		isFetching,
		isError,
		error,
		refetch,
	};
};
