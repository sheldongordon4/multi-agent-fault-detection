import type { QueryFunctionContext } from '@tanstack/react-query';
import api from '../../../shared/lib/api';
import type { TicketDetail, TicketListResponse } from '../../../shared/types';
import type { incidentQueryKeys } from '../utils/query-keys';

/**
 * GET /tickets — fault-ticket history (thin summaries, newest first).
 * The backend caps `limit` at 500 and has no cursor/pagination.
 */
export async function fetchIncidents({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof incidentQueryKeys.list>
>): Promise<TicketListResponse> {
	const [, , limit] = queryKey;

	const response = await api.get<TicketListResponse>('/tickets', {
		params: { limit },
	});

	return response.data;
}

/** GET /tickets/{incident_id} — summary + the full coordinator ticket in `raw`. */
export async function fetchIncident({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof incidentQueryKeys.detail>
>): Promise<TicketDetail> {
	const [, , incidentId] = queryKey;

	const response = await api.get<TicketDetail>(
		`/tickets/${encodeURIComponent(incidentId)}`
	);

	return response.data;
}
