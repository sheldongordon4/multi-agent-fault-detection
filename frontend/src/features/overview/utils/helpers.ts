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

export type SignalUnit = 'pu' | 'A';

/**
 * The smallest range the live chart will draw, as a fraction of the level
 * being plotted.
 *
 * Recharts' `['auto', 'auto']` domain fits the axis to the data, and on a
 * healthy bus the data is a flat line plus the RMS residue of the DFT — about
 * 2e-5 of the signal, peak to peak — which auto-scaling stretched to the full
 * chart height, so a quiet feeder read as violent oscillation. Pinning the
 * floor at 8e-5 of the level draws that residue at roughly a quarter of the
 * height: enough movement to read as live, not enough to read as a fault.
 * A real sag or fault current is orders of magnitude wider and opens the axis
 * up on its own.
 */
const MIN_SPAN_FRACTION = 8e-5;
/** So a bus reading exactly zero still gets a non-degenerate axis. */
const MIN_SPAN_ABSOLUTE: Record<SignalUnit, number> = { pu: 1e-5, A: 1e-3 };
const SPAN_PADDING = 0.05;

/**
 * A y-axis domain that holds a steady shape while the signal is quiet and
 * opens up when a fault comes through. Returns `undefined` when there is
 * nothing finite to plot, so the caller can fall back to recharts' own
 * behaviour.
 */
export function signalDomain(
	values: readonly (number | null | undefined)[],
	unit: SignalUnit
): [number, number] | undefined {
	let lo = Number.POSITIVE_INFINITY;
	let hi = Number.NEGATIVE_INFINITY;
	for (const value of values) {
		if (typeof value !== 'number' || !Number.isFinite(value)) continue;
		if (value < lo) lo = value;
		if (value > hi) hi = value;
	}
	if (!Number.isFinite(lo) || !Number.isFinite(hi)) return undefined;

	const floor = Math.max(MIN_SPAN_ABSOLUTE[unit], Math.abs(hi) * MIN_SPAN_FRACTION);
	const span = hi - lo;

	if (span < floor) {
		const mid = (lo + hi) / 2;
		lo = mid - floor / 2;
		hi = mid + floor / 2;
	} else {
		lo -= span * SPAN_PADDING;
		hi += span * SPAN_PADDING;
	}

	// Neither quantity is ever negative; a padded floor below zero is just
	// wasted chart height.
	return [Math.max(0, lo), hi];
}

/**
 * How many decimals the axis needs so that adjacent ticks differ. A 0.1 pu
 * span reads fine at three places; the 7e-5 span of a quiet bus needs six,
 * or every tick says 0.702. Amps drop to whole numbers once the span is wide
 * enough that a fraction of an amp is noise.
 */
export function signalDecimals(domain: readonly [number, number], unit: SignalUnit): number {
	const span = Math.abs(domain[1] - domain[0]);
	if (!Number.isFinite(span) || span === 0) return unit === 'pu' ? 3 : 0;
	const needed = Math.ceil(-Math.log10(span)) + 1;
	const minimum = unit === 'pu' ? 3 : 0;
	return Math.min(6, Math.max(minimum, needed));
}

/**
 * Axis and tooltip labels, at the precision the current axis needs. Amps get
 * digit grouping, since 1500 A of fault current is easier to read as 1,500.
 */
export function formatSignalValue(value: unknown, unit: SignalUnit, decimals = 3): string {
	const n = typeof value === 'number' ? value : Number(value);
	if (!Number.isFinite(n)) return '\u2014';
	return unit === 'pu'
		? n.toFixed(decimals)
		: n.toLocaleString(undefined, {
				minimumFractionDigits: decimals,
				maximumFractionDigits: decimals,
			});
}
