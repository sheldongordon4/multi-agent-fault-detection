import type { QueryFunctionContext } from '@tanstack/react-query';
import api from '@shared/lib/api';
import type { RepeatOffenderResponse } from '@shared/types';
import type { insightQueryKeys } from '../utils/query-keys';

/**
 * GET /tickets/repeat-offenders — buses producing the same fault code repeatedly.
 *
 * Declared before /tickets/{incident_id} on the server, which would otherwise
 * capture the path as an incident id.
 */
export async function fetchRepeatOffenders({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof insightQueryKeys.repeatOffenders>
>): Promise<RepeatOffenderResponse> {
	const [, , days, minOccurrences] = queryKey;

	const response = await api.get<RepeatOffenderResponse>(
		'/tickets/repeat-offenders',
		{ params: { days, min_occurrences: minOccurrences } }
	);

	return response.data;
}
