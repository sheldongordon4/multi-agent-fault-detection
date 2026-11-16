import { useQuery } from '@tanstack/react-query';
import { operatorsQueryOptions } from '../utils/query-options';

export const useFetchOperators = () => {
	const { data, isPending, isError, refetch } = useQuery({
		...operatorsQueryOptions(),
	});

	return {
		operators: data?.items ?? [],
		count: data?.count ?? 0,
		isPending,
		isError,
		refetch,
	};
};
