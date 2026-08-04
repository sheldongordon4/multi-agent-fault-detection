import { useQuery } from '@tanstack/react-query';
import { incidentQueryOptions } from '../utils/query-options';

export const useFetchIncident = (incidentId: string | null) => {
	const { data, isPending, isError, error, refetch } = useQuery({
		...incidentQueryOptions(incidentId ?? ''),
		enabled: Boolean(incidentId),
	});

	return { incident: data, isPending, isError, error, refetch };
};
