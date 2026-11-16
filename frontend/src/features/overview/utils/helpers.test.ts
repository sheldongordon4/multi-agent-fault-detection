import { describe, expect, it } from 'vitest';
import type { TicketSummary } from '@shared/types';
import {
	formatSignalValue,
	signalDecimals,
	signalDomain,
	summariseIncidents,
} from './helpers';

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

describe('signalDomain', () => {
	it('shows a quiet bus as a modest wobble, not a full-height sawtooth', () => {
		// The DFT residue on a healthy bus is ~1.6e-5 pu peak to peak. Under
		// recharts' auto domain that filled the whole chart; here it should
		// take up a fraction of the height and stay centred on the data.
		const readings = [0.702108, 0.702124, 0.70211, 0.702122];
		const [lo, hi] = signalDomain(readings, 'pu')!;

		const span = hi - lo;
		const wobble = Math.max(...readings) - Math.min(...readings);
		expect(wobble / span).toBeGreaterThan(0.2);
		expect(wobble / span).toBeLessThan(0.5);
		expect(lo).toBeLessThan(0.702108);
		expect(hi).toBeGreaterThan(0.702124);
	});

	it('opens up when a sag exceeds the floor', () => {
		const [lo, hi] = signalDomain([1.0, 1.0, 0.7, 0.72, 1.0], 'pu')!;

		expect(lo).toBeLessThan(0.7);
		expect(hi).toBeGreaterThan(1.0);
		expect(hi - lo).toBeGreaterThan(0.3);
	});

	it('floors amps relative to the level being plotted', () => {
		const [lo, hi] = signalDomain([500, 500.001, 499.999], 'A')!;

		expect(hi - lo).toBeCloseTo(500.001 * 8e-5, 9);
	});

	it('never dips below zero for a bus reading nothing', () => {
		// b675's phase-A current is exported as 0 under every scenario.
		const [lo, hi] = signalDomain([0, 0, 0], 'A')!;

		expect(lo).toBe(0);
		expect(hi).toBeGreaterThan(0);
	});

	it('ignores non-finite readings and gives up when nothing is left', () => {
		expect(signalDomain([null, undefined, Number.NaN], 'pu')).toBeUndefined();
		expect(signalDomain([Number.NaN, 1.0, 1.0], 'pu')![1]).toBeGreaterThan(1.0);
	});
});

describe('signalDecimals', () => {
	it('keeps three places on a wide per-unit axis and adds more as it narrows', () => {
		expect(signalDecimals([0.65, 0.75], 'pu')).toBe(3);
		// The quiet-bus case: a 7e-5 span at three places prints 0.702 on
		// every tick.
		expect(signalDecimals([0.70208, 0.70215], 'pu')).toBe(6);
	});

	it('uses whole amps on a wide axis and fractions on a narrow one', () => {
		expect(signalDecimals([300, 1600], 'A')).toBe(0);
		expect(signalDecimals([335.98, 336.02], 'A')).toBe(3);
	});
});

describe('formatSignalValue', () => {
	it('reads per unit at the requested precision and amps with grouping', () => {
		expect(formatSignalValue(0.702124, 'pu')).toBe('0.702');
		expect(formatSignalValue(0.702124, 'pu', 6)).toBe('0.702124');
		expect(formatSignalValue(1499.6, 'A', 0)).toBe(
			(1500).toLocaleString(undefined, { maximumFractionDigits: 0 })
		);
	});

	it('shows a dash for anything unreadable', () => {
		expect(formatSignalValue(undefined, 'pu')).toBe('\u2014');
		expect(formatSignalValue('abc', 'A')).toBe('\u2014');
	});
});
