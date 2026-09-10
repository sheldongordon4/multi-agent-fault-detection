import { describe, expect, it } from 'vitest';
import type { RepeatOffender } from '@shared/types';
import { formatCadence, offenderSubtitle } from './helpers';

function offender(overrides: Partial<RepeatOffender> = {}): RepeatOffender {
	return {
		bus_id: 'b671',
		fault_code: 'SLG',
		occurrences: 3,
		first_seen: '2026-09-01T00:00:00Z',
		last_seen: '2026-09-08T00:00:00Z',
		worst_severity: 'high',
		customers_affected: 6400,
		mean_days_between: 3.5,
		recent_incident_ids: ['i-3', 'i-2', 'i-1'],
		...overrides,
	};
}

describe('formatCadence', () => {
	it('names sub-daily recurrence rather than numbering it', () => {
		// "every ~0.2 days" is arithmetic, not information.
		expect(formatCadence(offender({ mean_days_between: 0.2 }))).toBe('several a day');
	});

	it('reads about daily just above a day', () => {
		expect(formatCadence(offender({ mean_days_between: 1.4 }))).toBe('about daily');
	});

	it('keeps one decimal while the number is small', () => {
		expect(formatCadence(offender({ mean_days_between: 3.5 }))).toBe('every ~3.5 days');
	});

	it('rounds once the interval is long enough that precision is noise', () => {
		expect(formatCadence(offender({ mean_days_between: 18.24 }))).toBe('every ~18 days');
	});

	it('says nothing when there is no cadence to report', () => {
		// A single incident, or several replayed at the same instant.
		expect(formatCadence(offender({ mean_days_between: null }))).toBeNull();
		expect(formatCadence(offender({ mean_days_between: 0 }))).toBeNull();
	});
});

describe('offenderSubtitle', () => {
	it('leads with impact, because that is what picks the next inspection', () => {
		expect(offenderSubtitle(offender({ customers_affected: 11800 }))).toBe(
			'11,800 customers · every ~3.5 days'
		);
	});

	it('omits impact rather than showing a bus with no known count as zero', () => {
		expect(offenderSubtitle(offender({ customers_affected: null }))).toBe(
			'every ~3.5 days'
		);
	});

	it('degrades to an empty string when neither half is known', () => {
		const bare = offender({ customers_affected: null, mean_days_between: null });
		expect(offenderSubtitle(bare)).toBe('');
	});
});
