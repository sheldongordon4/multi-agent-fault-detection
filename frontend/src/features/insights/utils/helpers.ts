import type { RepeatOffender } from '@shared/types';

/**
 * How often a bus is reoffending, in words.
 *
 * The backend measures the mean gap across the incidents themselves rather than
 * across the lookback window, so the value can be a fraction of a day. "every
 * ~0.2 days" is arithmetic, not information — an operator reads cadence to
 * judge urgency, so sub-daily recurrence is named rather than numbered.
 */
export function formatCadence(offender: RepeatOffender): string | null {
	const days = offender.mean_days_between;
	if (days == null || days <= 0) return null;

	if (days < 1) return 'several a day';
	if (days < 2) return 'about daily';
	if (days < 10) return `every ~${days.toFixed(1)} days`;
	return `every ~${Math.round(days)} days`;
}

/**
 * The one-line subtitle under a repeat offender.
 *
 * Impact first: an operator scanning this list is choosing what to inspect
 * next, and 11,800 customers decides that faster than a recurrence interval.
 */
export function offenderSubtitle(offender: RepeatOffender): string {
	const parts: string[] = [];

	if (offender.customers_affected != null) {
		parts.push(`${offender.customers_affected.toLocaleString()} customers`);
	}

	const cadence = formatCadence(offender);
	if (cadence) parts.push(cadence);

	return parts.join(' · ');
}
