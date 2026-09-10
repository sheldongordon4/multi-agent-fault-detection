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

/**
 * What each classifier code actually means, in operator language.
 *
 * The models emit terse codes — `SLG`, `OPEN_2PH` — which are unreadable to
 * anyone who is not a protection engineer, and the console shows them on the
 * map, in the incident list and on the fault-type chart. This is the one place
 * that translates them.
 *
 * `signature` is what the detector keys on, drawn from the same physics the SOPs
 * describe: zero-sequence current (I0/I1) means a ground path, negative-sequence
 * (I2/I1) means unbalance, and both near zero with a deep sag means the fault is
 * balanced. Worth surfacing — it is the reason the classifier chose this label.
 */
export interface FaultTypeInfo {
	/** Full name, spelled out. */
	name: string;
	/** One line: what physically happened on the line. */
	description: string;
	/** The electrical signature that identifies it. */
	signature: string;
}

export const FAULT_TYPES: Record<string, FaultTypeInfo> = {
	SLG: {
		name: 'Single line-to-ground',
		description:
			'One phase conductor in contact with ground. The most common fault on overhead distribution.',
		signature: 'Zero-sequence current elevated; one phase sags.',
	},
	LL: {
		name: 'Line-to-line',
		description:
			'Two phase conductors shorted together, with no path to ground — often conductor slap or a tree limb.',
		signature: 'Negative-sequence elevated, zero-sequence near zero.',
	},
	LLG: {
		name: 'Double line-to-ground',
		description:
			'Two phases faulted to ground. Carries more current than a single-phase fault and more often damages equipment.',
		signature: 'Both zero- and negative-sequence elevated.',
	},
	LLL: {
		name: 'Three-phase',
		description:
			'All three phases shorted together. The rarest fault and the most severe — the highest current the feeder can deliver.',
		signature: 'Deep sag on all three phases, sequence ratios near zero.',
	},
	LLLG: {
		name: 'Three-phase to ground',
		description:
			'All three phases faulted to ground. Behaves much like a three-phase fault; the ground path adds zero-sequence current.',
		signature: 'Deep balanced sag with a ground return.',
	},
	OPEN_1PH: {
		name: 'Open conductor — one phase',
		description:
			'One phase interrupted: a broken conductor, blown fuse or failed splice. Downstream three-phase motors single-phase and overheat.',
		signature: 'Current near zero on one phase while its voltage persists.',
	},
	OPEN_2PH: {
		name: 'Open conductor — two phases',
		description: 'Two phases interrupted. Severe unbalance with little or no fault current.',
		signature: 'Unbalance without the overcurrent a short circuit produces.',
	},
	OPEN_3PH: {
		name: 'Open conductor — three phases',
		description:
			'All three phases interrupted — usually presents simply as loss of supply downstream.',
		signature: 'Current collapses on all phases; voltage may float.',
	},
	UNKNOWN: {
		name: 'Unclassified',
		description:
			'The detector flagged a disturbance the classifier could not place — or no classification was attached.',
		signature: 'No matching signature.',
	},
};

/** Description for a code, falling back to `UNKNOWN` rather than throwing. */
export function faultTypeInfo(code: string | null | undefined): FaultTypeInfo {
	const key = formatFaultCode(code);
	return FAULT_TYPES[key] ?? FAULT_TYPES.UNKNOWN;
}
