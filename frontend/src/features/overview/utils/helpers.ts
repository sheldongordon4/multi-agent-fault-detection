import type { TicketSummary } from '@shared/types';
import { normalizeSeverity } from '@features/incidents/utils/helpers';

export interface OverviewCounts {
	total: number;
	high: number;
	medium: number;
	low: number;
	/** Null when no open incident sits at a bus with a known customer count. */
	customersAffected: number | null;
}

/** A ticket whose work is finished no longer has customers off supply. */
const CLOSED_STATUSES = new Set(['resolved']);

/**
 * Collapse the incident list into the numbers the tiles show.
 *
 * Customers affected is a MAX, not a sum, and that is the whole reason this
 * lives in a tested function rather than inline in the page. On a radial feeder
 * the downstream customer sets NEST — everything below b671 is also below b650
 * — so adding two open faults counts the same households twice and can report
 * more customers out than the feeder serves. The most upstream open fault
 * defines the affected set on its own.
 *
 * That stops being true the moment a second feeder is modelled, since two
 * feeders' customers are disjoint. At that point this becomes a max per feeder
 * and a sum across them.
 */
export function summariseIncidents(incidents: TicketSummary[]): OverviewCounts {
	let high = 0;
	let medium = 0;
	let low = 0;
	let customersAffected: number | null = null;

	for (const incident of incidents) {
		const severity = normalizeSeverity(incident.severity);
		if (severity === 'high') high += 1;
		else if (severity === 'medium') medium += 1;
		else low += 1;

		const affected = incident.customers_affected;
		const open = !CLOSED_STATUSES.has(String(incident.status ?? '').toLowerCase());
		if (open && typeof affected === 'number') {
			customersAffected = Math.max(customersAffected ?? 0, affected);
		}
	}

	return { total: incidents.length, high, medium, low, customersAffected };
}
