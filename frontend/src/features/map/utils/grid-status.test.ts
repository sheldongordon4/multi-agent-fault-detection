import { describe, expect, it } from 'vitest';
import type { TicketSummary } from '@shared/types';
import {
	deriveBusStatuses,
	deriveParishSeverity,
	formatAge,
	HEALTHY_COLOR,
	recencyWeight,
	SEVERITY_COLOR,
	statusColor,
} from './grid-status';

function ticket(over: Partial<TicketSummary> = {}): TicketSummary {
	return {
		incident_id: 'SCN_0001',
		ticket_id: 'T1',
		scenario: 'ieee13',
		bus_id: 'b650',
		fault_type: 'SLG',
		severity: 'medium',
		status: 'diagnosed',
		summary: 'summary',
		created_at: '2026-08-16T10:00:00Z',
		...over,
	};
}

describe('deriveBusStatuses', () => {
	it('returns every mapped bus, including ones with no incidents', () => {
		const statuses = deriveBusStatuses([]);
		expect(statuses.length).toBeGreaterThan(0);
		expect(statuses.every((s) => s.severity === null)).toBe(true);
		// A healthy site must still be visible — an operator needs to see that a
		// substation is fine, not merely that it's absent from the list.
		expect(statuses.map((s) => s.busId)).toContain('b650');
	});

	it('keeps the worst severity when a bus has several incidents', () => {
		const statuses = deriveBusStatuses([
			ticket({ incident_id: 'a', severity: 'low' }),
			ticket({ incident_id: 'b', severity: 'high' }),
			ticket({ incident_id: 'c', severity: 'medium' }),
		]);
		const b650 = statuses.find((s) => s.busId === 'b650');
		expect(b650?.severity).toBe('high');
		expect(b650?.activeCount).toBe(3);
	});

	it('ignores resolved tickets', () => {
		// History, not current grid state: colouring a site red for faults that
		// were already cleared would cry wolf.
		const statuses = deriveBusStatuses([
			ticket({ incident_id: 'a', severity: 'high', status: 'resolved' }),
		]);
		const b650 = statuses.find((s) => s.busId === 'b650');
		expect(b650?.severity).toBeNull();
		expect(b650?.activeCount).toBe(0);
	});

	it('tracks the newest incident, not merely the last seen', () => {
		const statuses = deriveBusStatuses([
			ticket({ incident_id: 'older', created_at: '2026-08-16T10:00:00Z' }),
			ticket({ incident_id: 'newest', created_at: '2026-08-16T12:00:00Z' }),
			ticket({ incident_id: 'middle', created_at: '2026-08-16T11:00:00Z' }),
		]);
		const b650 = statuses.find((s) => s.busId === 'b650');
		expect(b650?.latestIncidentId).toBe('newest');
	});

	it('coerces unknown severity strings the same way the backend does', () => {
		const statuses = deriveBusStatuses([
			ticket({ severity: 'critical' }), // synonym for high
		]);
		expect(statuses.find((s) => s.busId === 'b650')?.severity).toBe('high');
	});

	it('skips incidents with no bus', () => {
		const statuses = deriveBusStatuses([ticket({ bus_id: null })]);
		expect(statuses.every((s) => s.activeCount === 0)).toBe(true);
	});
});

describe('deriveParishSeverity', () => {
	it('tints a parish with the worst severity among its buses', () => {
		const statuses = deriveBusStatuses([
			ticket({ incident_id: 'a', bus_id: 'b650', severity: 'low' }),
			ticket({ incident_id: 'b', bus_id: 'b650', severity: 'high' }),
		]);
		expect(deriveParishSeverity(statuses).Kingston).toBe('high');
	});

	it('omits parishes with nothing active, so only faulted ones get labelled', () => {
		expect(deriveParishSeverity(deriveBusStatuses([]))).toEqual({});
	});
});

describe('recencyWeight', () => {
	const now = Date.parse('2026-08-16T12:00:00Z');

	it('draws a brand new incident at full strength', () => {
		expect(recencyWeight('2026-08-16T12:00:00Z', now)).toBeCloseTo(1);
	});

	it('fades with age and bottoms out rather than vanishing', () => {
		const fresh = recencyWeight('2026-08-16T11:55:00Z', now);
		const older = recencyWeight('2026-08-16T11:40:00Z', now);
		const stale = recencyWeight('2026-08-16T06:00:00Z', now);
		expect(fresh).toBeGreaterThan(older);
		expect(older).toBeGreaterThan(stale);
		expect(stale).toBeCloseTo(0.35);
	});

	it('falls back to full strength for missing or unparseable timestamps', () => {
		expect(recencyWeight(null, now)).toBe(1);
		expect(recencyWeight('not a date', now)).toBe(1);
	});
});

describe('formatAge', () => {
	const now = Date.parse('2026-08-16T12:00:00Z');

	it('scales the unit with the gap', () => {
		expect(formatAge('2026-08-16T11:59:30Z', now)).toBe('30s ago');
		expect(formatAge('2026-08-16T11:45:00Z', now)).toBe('15m ago');
		expect(formatAge('2026-08-16T09:00:00Z', now)).toBe('3h ago');
		expect(formatAge('2026-08-14T12:00:00Z', now)).toBe('2d ago');
	});

	it('is empty when there is no timestamp', () => {
		expect(formatAge(null, now)).toBe('');
	});
});

describe('statusColor', () => {
	it('maps severity to its colour and null to healthy', () => {
		expect(statusColor('high')).toBe(SEVERITY_COLOR.high);
		expect(statusColor(null)).toBe(HEALTHY_COLOR);
	});
});
