import { fetchIncident, fetchIncidents } from '../services/incident-service';
import { incidentQueryKeys } from './query-keys';

export const DEFAULT_INCIDENT_LIMIT = 50;

export const incidentsQueryOptions = (limit: number = DEFAULT_INCIDENT_LIMIT) => ({
	queryKey: incidentQueryKeys.list(limit),
	queryFn: fetchIncidents,
});

/**
 * Detail is deliberately NOT seeded from the list cache: the list returns the
 * thin `TicketSummary` projection, which has no `raw` — seeding it would render
 * a detail panel with no root cause, actions, evidence, or citations.
 */
export const incidentQueryOptions = (incidentId: string) => ({
	queryKey: incidentQueryKeys.detail(incidentId),
	queryFn: fetchIncident,
});
