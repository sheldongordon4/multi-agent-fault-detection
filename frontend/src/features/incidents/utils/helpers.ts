import type { Severity, TicketStatus, TicketSummary } from '@shared/types';
import type { SeverityFilter, StatusFilter } from '../store/incident-slice';

/**
 * Mirrors `_SEVERITY_SYNONYMS` in app/faults/schemas.py.
 *
 * This map is NOT optional: the coordinator's free-form output is coerced by
 * Pydantic, but the persisted column stores the raw string, so `GET /tickets`
 * really does return values like "moderate" or "critical". Without this,
 * "critical" would fall through to the default and display as MEDIUM.
 */
const SEVERITY_SYNONYMS: Record<string, Severity> = {
	info: 'low',
	informational: 'low',
	minor: 'low',
	low: 'low',
	medium: 'medium',
	moderate: 'medium',
	med: 'medium',
	elevated: 'medium',
	high: 'high',
	critical: 'high',
	severe: 'high',
	major: 'high',
};

export function normalizeSeverity(value: string | null | undefined): Severity {
	const key = (value ?? '').trim().toLowerCase();
	// Same fallback as the backend: unknown severities are treated as medium.
	return SEVERITY_SYNONYMS[key] ?? 'medium';
}

export function normalizeStatus(value: string | null | undefined): TicketStatus {
	const v = (value ?? '').trim().toLowerCase();
	if (v === 'diagnosed' || v === 'acknowledged' || v === 'resolved') return v;
	return 'diagnosed';
}

/** Rank used to sort/threshold by urgency. */
export const SEVERITY_RANK: Record<Severity, number> = {
	high: 3,
	medium: 2,
	low: 1,
};

/**
 * Client-side filtering. The list endpoint has no query params beyond `limit`,
 * so search/severity/status are applied in the browser over the fetched page.
 */
export function filterIncidents(
	incidents: TicketSummary[],
	{
		search,
		severity,
		status,
		bus = null,
	}: {
		search: string;
		severity: SeverityFilter;
		status: StatusFilter;
		/** Spatial filter set by clicking a substation on the grid map. */
		bus?: string | null;
	}
): TicketSummary[] {
	const needle = search.trim().toLowerCase();

	return incidents.filter((incident) => {
		if (bus && incident.bus_id !== bus) return false;

		if (severity !== 'all' && normalizeSeverity(incident.severity) !== severity) {
			return false;
		}

		if (status !== 'all' && normalizeStatus(incident.status) !== status) {
			return false;
		}

		if (!needle) return true;

		return [
			incident.incident_id,
			incident.ticket_id,
			incident.bus_id,
			incident.fault_type,
			incident.scenario,
			incident.summary,
		]
			.filter(Boolean)
			.some((field) => String(field).toLowerCase().includes(needle));
	});
}

/** Compact absolute timestamp — operators need the real clock time, not "2h ago". */
export function formatTimestamp(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return '—';

	return date.toLocaleString(undefined, {
		month: 'short',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hour12: false,
	});
}

/**
 * The backend stores fault_type as prose — e.g. "LLG near b684 (~0.061 km)" —
 * so the leading token is the actual classification code (SLG, LL, LLG, LLL,
 * LLLG, OPEN_1PH...). Use the code alone where space is tight.
 */
export function formatFaultCode(value: string | null | undefined): string {
	const text = (value ?? '').trim();
	if (!text) return 'UNKNOWN';
	return (text.split(/\s+/)[0] ?? text).toUpperCase();
}

/** Full fault description, untouched apart from trimming (detail view). */
export function formatFaultType(value: string | null | undefined): string {
	const text = (value ?? '').trim();
	return text || 'Unknown';
}
