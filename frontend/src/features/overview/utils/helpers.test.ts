import { describe, expect, it } from 'vitest';
import type { TicketSummary } from '@shared/types';
import { summariseIncidents } from './helpers';

function ticket(overrides: Partial<TicketSummary> = {}): TicketSummary {
	return {
		incident_id: 'i-1',
		ticket_id: 't-1',
		scenario: 'feeder:ieee13',
		bus_id: 'b671',
		fault_type: 'SLG near b671',
		severity: 'high',
		status: 'diagnosed',
		summary: null,
		created_at: '2026-09-10T00:00:00Z',
		...overrides,
	};
}

describe('summariseIncidents', () => {
	it('counts incidents by severity', () => {
		const counts = summariseIncidents([
			ticket({ severity: 'high' }),
			ticket({ severity: 'critical' }), // synonym, ranks as high
			ticket({ severity: 'medium' }),
			ticket({ severity: 'low' }),
		]);

		expect(counts).toMatchObject({ total: 4, high: 2, medium: 1, low: 1 });
	});

	it('takes the largest downstream set rather than adding them up', () => {
		// The bug this prevents: b671's customers are a subset of b650's, so
		// summing reports 20,600 out on a feeder that serves 14,200.
		const counts = summariseIncidents([
			ticket({ incident_id: 'i-1', bus_id: 'b650', customers_affected: 14200 }),
			ticket({ incident_id: 'i-2', bus_id: 'b671', customers_affected: 6400 }),
		]);

		expect(counts.customersAffected).toBe(14200);
	});

	it('ignores resolved incidents', () => {
		const counts = summariseIncidents([
			ticket({ status: 'resolved', customers_affected: 14200 }),
			ticket({ status: 'diagnosed', customers_affected: 980 }),
		]);

		expect(counts.customersAffected).toBe(980);
	});

	it('reports nothing rather than zero when no impact is known', () => {
		// Zero would read as "no customers affected", which is a claim. Absent
		// is the truth when the buses are not in the customer table.
		const counts = summariseIncidents([ticket({ customers_affected: null })]);

		expect(counts.customersAffected).toBeNull();
	});

	it('reports nothing for an empty list', () => {
		expect(summariseIncidents([])).toEqual({
			total: 0,
			high: 0,
			medium: 0,
			low: 0,
			customersAffected: null,
		});
	});

	it('still counts an open incident whose impact is unknown', () => {
		const counts = summariseIncidents([
			ticket({ bus_id: 'b999', customers_affected: null }),
			ticket({ incident_id: 'i-2', bus_id: 'b675', customers_affected: 980 }),
		]);

		expect(counts.total).toBe(2);
		expect(counts.customersAffected).toBe(980);
	});
});
