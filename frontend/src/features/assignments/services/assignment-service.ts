import type { QueryFunctionContext } from '@tanstack/react-query';
import api from '@shared/lib/api';
import type {
	Assignment,
	AssignmentEvent,
	AssignmentEventListResponse,
	AssignmentListResponse,
	AssignmentUpdate,
	OperatorListResponse,
} from '@shared/types';
import type { assignmentQueryKeys, operatorQueryKeys } from '../utils/query-keys';

/** GET /assignments — tickets joined to their assignment row, filtered in SQL. */
export async function fetchAssignments({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof assignmentQueryKeys.list>
>): Promise<AssignmentListResponse> {
	const [, , filters] = queryKey;

	const params: Record<string, string | boolean | number> = {};
	if (filters.workState !== 'all') params.work_state = filters.workState;
	if (filters.severity !== 'all') params.severity = filters.severity;
	if (filters.priority !== 'all') params.priority = filters.priority;
	if (filters.search.trim()) params.q = filters.search.trim();

	// 'unassigned' is a distinct filter server-side, not an assignee id.
	if (filters.assignee === 'unassigned') params.unassigned = true;
	else if (filters.assignee !== 'all') params.assignee_id = filters.assignee;

	const response = await api.get<AssignmentListResponse>('/assignments', {
		params,
	});

	return response.data;
}

/** GET /assignments/{incident_id} — one ticket joined to its assignment row. */
export async function fetchAssignment({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof assignmentQueryKeys.detail>
>): Promise<Assignment> {
	const [, , incidentId] = queryKey;

	const response = await api.get<Assignment>(
		`/assignments/${encodeURIComponent(incidentId)}`
	);

	return response.data;
}

/** GET /operators — the roster with open-ticket counts. */
export async function fetchOperators({
	queryKey: _queryKey,
}: QueryFunctionContext<
	ReturnType<typeof operatorQueryKeys.list>
>): Promise<OperatorListResponse> {
	const response = await api.get<OperatorListResponse>('/operators');
	return response.data;
}

/** GET /assignments/{id}/events — the activity feed, oldest first. */
export async function fetchAssignmentEvents({
	queryKey,
}: QueryFunctionContext<
	ReturnType<typeof assignmentQueryKeys.events>
>): Promise<AssignmentEventListResponse> {
	const [, , incidentId] = queryKey;

	const response = await api.get<AssignmentEventListResponse>(
		`/assignments/${encodeURIComponent(incidentId)}/events`
	);

	return response.data;
}

/**
 * PATCH /assignments/{id}.
 *
 * `actorId` goes in `X-Actor-Id` so the activity log can attribute the change.
 * There is no auth to derive it from — the console claims it (see the store's
 * `actingOperatorId`).
 */
export async function updateAssignment({
	incidentId,
	patch,
	actorId,
}: {
	incidentId: string;
	patch: AssignmentUpdate;
	actorId: string | null;
}): Promise<Assignment> {
	const response = await api.patch<Assignment>(
		`/assignments/${encodeURIComponent(incidentId)}`,
		patch,
		actorId ? { headers: { 'X-Actor-Id': actorId } } : undefined
	);

	return response.data;
}

/** POST /assignments/{id}/comments — appends to the activity feed. */
export async function addComment({
	incidentId,
	body,
	actorId,
}: {
	incidentId: string;
	body: string;
	actorId: string | null;
}): Promise<AssignmentEvent> {
	const response = await api.post<AssignmentEvent>(
		`/assignments/${encodeURIComponent(incidentId)}/comments`,
		{ body },
		actorId ? { headers: { 'X-Actor-Id': actorId } } : undefined
	);

	return response.data;
}
