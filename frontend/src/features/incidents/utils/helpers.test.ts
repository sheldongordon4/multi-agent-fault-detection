import { describe, expect, it } from 'vitest';
import type { TicketSummary } from '@shared/types';
import {
	filterIncidents,
	formatFaultCode,
	normalizeSeverity,
	normalizeStatus,
	SEVERITY_RANK,
} from './helpers';

function ticket(over: Partial<TicketSummary> = {}): TicketSummary {
	return {
		incident_id: 'SCN_0001',
		ticket_id: 'T1',
		scenario: 'ieee13',
		bus_id: 'b650',
		fault_type: 'SLG',
		severity: 'medium',
		status: 'diagnosed',
		summary: 'voltage sag on the feeder',
		created_at: '2026-08-16T10:00:00Z',
		...over,
	};
}

const ALL = { search: '', severity: 'all', status: 'all' } as const;

describe('normalizeSeverity', () => {
	it('accepts the backend synonyms', () => {
		// Mirrors _SEVERITY_SYNONYMS in app/faults/schemas.py — the persisted column
		// keeps the coordinator's raw string, so "critical" really does arrive.
		expect(normalizeSeverity('critical')).toBe('high');
		expect(normalizeSeverity('moderate')).toBe('medium');
		expect(normalizeSeverity('informational')).toBe('low');
	});

	it('is case and whitespace tolerant', () => {
		expect(normalizeSeverity('  HIGH ')).toBe('high');
	});

	it('falls back to medium for unknown or missing values, as the backend does', () => {
		expect(normalizeSeverity('wat')).toBe('medium');
		expect(normalizeSeverity(null)).toBe('medium');
	});
});

describe('normalizeStatus', () => {
	it('passes through known statuses and defaults the rest to diagnosed', () => {
		expect(normalizeStatus('resolved')).toBe('resolved');
		expect(normalizeStatus('ACKNOWLEDGED')).toBe('acknowledged');
		expect(normalizeStatus('nonsense')).toBe('diagnosed');
		expect(normalizeStatus(null)).toBe('diagnosed');
	});
});

describe('SEVERITY_RANK', () => {
	it('orders severities so "worst wins" comparisons hold', () => {
		expect(SEVERITY_RANK.high).toBeGreaterThan(SEVERITY_RANK.medium);
		expect(SEVERITY_RANK.medium).toBeGreaterThan(SEVERITY_RANK.low);
	});
});

describe('filterIncidents', () => {
	const incidents = [
		ticket({ incident_id: 'a', bus_id: 'b650', severity: 'high' }),
		ticket({ incident_id: 'b', bus_id: 'b675', severity: 'low' }),
		ticket({ incident_id: 'c', bus_id: 'b675', status: 'resolved' }),
	];

	it('returns everything when no filter is set', () => {
		expect(filterIncidents(incidents, ALL)).toHaveLength(3);
	});

	it('filters by bus — the map click path', () => {
		const out = filterIncidents(incidents, { ...ALL, bus: 'b675' });
		expect(out.map((i) => i.incident_id)).toEqual(['b', 'c']);
	});

	it('treats a null bus as no spatial filter', () => {
		expect(filterIncidents(incidents, { ...ALL, bus: null })).toHaveLength(3);
	});

	it('filters by severity using the normalized value', () => {
		const out = filterIncidents(
			[ticket({ incident_id: 'x', severity: 'critical' })],
			{ ...ALL, severity: 'high' }
		);
		expect(out).toHaveLength(1);
	});

	it('filters by status', () => {
		const out = filterIncidents(incidents, { ...ALL, status: 'resolved' });
		expect(out.map((i) => i.incident_id)).toEqual(['c']);
	});

	it('searches across id, bus, fault type and summary', () => {
		expect(filterIncidents(incidents, { ...ALL, search: 'b675' })).toHaveLength(2);
		expect(filterIncidents(incidents, { ...ALL, search: 'sag' })).toHaveLength(3);
		expect(filterIncidents(incidents, { ...ALL, search: 'SLG' })).toHaveLength(3);
	});

	it('ignores case and surrounding whitespace in the search', () => {
		expect(filterIncidents(incidents, { ...ALL, search: '  B675 ' })).toHaveLength(2);
	});

	it('combines filters conjunctively', () => {
		const out = filterIncidents(incidents, {
			...ALL,
			bus: 'b675',
			status: 'resolved',
		});
		expect(out.map((i) => i.incident_id)).toEqual(['c']);
	});
});

describe('formatFaultCode', () => {
	it('shortens a decorated fault type to its code', () => {
		// The coordinator writes "SLG near b650"; the list column only has room
		// for the code.
		expect(formatFaultCode('SLG near b650')).toBe('SLG');
	});

	it('has a fallback for missing values', () => {
		expect(formatFaultCode(null)).toBeTruthy();
	});
});
