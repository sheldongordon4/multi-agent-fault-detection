import { useQuery } from '@tanstack/react-query';
import {
	DEFAULT_MIN_OCCURRENCES,
	DEFAULT_WINDOW_DAYS,
	repeatOffendersQueryOptions,
} from '../utils/query-options';

export const useFetchRepeatOffenders = (
	days: number = DEFAULT_WINDOW_DAYS,
	minOccurrences: number = DEFAULT_MIN_OCCURRENCES
) => {
	const { data, isPending, isError, refetch } = useQuery({
		...repeatOffendersQueryOptions(days, minOccurrences),
	});

	return {
		offenders: data?.items ?? [],
		count: data?.count ?? 0,
		windowDays: data?.window_days ?? days,
		isPending,
		isError,
		refetch,
	};
};
