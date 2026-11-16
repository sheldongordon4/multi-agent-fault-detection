import { fetchRepeatOffenders } from '../services/insight-service';
import { insightQueryKeys } from './query-keys';

/** Long enough to be a pattern, short enough that a fixed fault drops off it. */
export const DEFAULT_WINDOW_DAYS = 30;

/** Two of the same fault at one bus is the smallest thing that is not a one-off. */
export const DEFAULT_MIN_OCCURRENCES = 2;

export const repeatOffendersQueryOptions = (
	days: number = DEFAULT_WINDOW_DAYS,
	minOccurrences: number = DEFAULT_MIN_OCCURRENCES
) => ({
	queryKey: insightQueryKeys.repeatOffenders(days, minOccurrences),
	queryFn: fetchRepeatOffenders,
});
