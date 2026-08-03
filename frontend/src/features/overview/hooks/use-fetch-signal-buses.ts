import { useQuery } from '@tanstack/react-query';
import { fetchSignalBuses } from '../services/signal-service';
import { signalQueryKeys } from '../utils/query-keys';

/**
 * Buses are discovered from live traffic, so the list grows as producers publish.
 * Poll periodically rather than caching indefinitely — otherwise a bus that
 * starts streaming after page load would never appear in the selector.
 */
export const useFetchSignalBuses = () => {
	const { data, isPending, isError } = useQuery({
		queryKey: signalQueryKeys.buses(),
		queryFn: fetchSignalBuses,
		refetchInterval: 15_000,
		staleTime: 10_000,
	});

	return {
		buses: data?.items ?? [],
		isPending,
		isError,
	};
};
