import { describe, expect, it } from 'vitest';
import type { Assignment } from '@shared/types';
import {
	avatarClass,
	formatAge,
	impliedWorkState,
	initialsOf,
	readSla,
} from './helpers';

const BASE: Assignment = {
	incident_id: 'ieee13:b671:1',
	ticket_id: 'T-1',
	bus_id: 'b671',
	scenario: 'feeder:ieee13',
	fault_type: 'SLG near b671',
	severity: 'high',
	status: 'diagnosed',
	summary: 'Phase-A to ground.',
	created_at: '2026-09-04T12:00:00Z',
	work_state: 'assigned',
	priority: 'p1',
	assignee_id: 'op-1',
	assignee_name: 'K. Reid',
	assignee_initials: 'KR',
	due_at: '2026-09-04T12:30:00Z',
	note: null,
	version: 1,
	updated_at: null,
};

const NOON = Date.parse('2026-09-04T12:00:00Z');

describe('formatAge', () => {
	it('stays compact across minutes, hours and days', () => {
		expect(formatAge('2026-09-04T11:57:00Z', NOON)).toBe('3m');
		expect(formatAge('2026-09-04T10:48:00Z', NOON)).toBe('1h 12m');
		expect(formatAge('2026-09-04T09:00:00Z', NOON)).toBe('3h');
		expect(formatAge('2026-09-02T12:00:00Z', NOON)).toBe('2d');
	});

	it('handles missing and malformed timestamps', () => {
		expect(formatAge(null, NOON)).toBe('—');
		expect(formatAge('not a date', NOON)).toBe('—');
	});

	it('never reports a negative age for a clock-skewed future timestamp', () => {
		expect(formatAge('2026-09-04T12:05:00Z', NOON)).toBe('0m');
	});
});

describe('readSla', () => {
	it('counts down while work is live', () => {
		const reading = readSla(BASE, NOON);
		expect(reading.state).toBe('due');
		expect(reading.label).toBe('30m left');
	});

	it('reports overdue work as over, not as a negative countdown', () => {
		const reading = readSla(BASE, Date.parse('2026-09-04T12:36:00Z'));
		expect(reading.state).toBe('over');
		expect(reading.label).toBe('6m over');
	});

	it('pauses the clock while a ticket is blocked', () => {
		// A clock that runs while a transformer waits on a lab result is
		// measuring the lab, not the operator.
		const reading = readSla(
			{ ...BASE, work_state: 'blocked' },
			Date.parse('2026-09-05T00:00:00Z')
		);
		expect(reading.state).toBe('paused');
	});

	it('stops counting once the work is terminal', () => {
		for (const state of ['resolved', 'closed'] as const) {
			const reading = readSla(
				{ ...BASE, work_state: state },
				Date.parse('2026-09-05T00:00:00Z')
			);
			expect(reading.state).toBe('met');
		}
	});

	it('has nothing to say without a due date', () => {
		expect(readSla({ ...BASE, due_at: null }, NOON).state).toBe('none');
	});
});

describe('initialsOf', () => {
	it('takes first and last initials, or two letters from one name', () => {
		expect(initialsOf('K. Reid')).toBe('KR');
		expect(initialsOf('Kemar Anthony Reid')).toBe('KR');
		expect(initialsOf('Kemar')).toBe('KE');
	});

	it('degrades rather than throwing on empty input', () => {
		expect(initialsOf(null)).toBe('—');
		expect(initialsOf('   ')).toBe('—');
	});
});

describe('avatarClass', () => {
	it('is stable for the same operator and neutral when unassigned', () => {
		// Colour is hashed from the id, not the list position, so reordering the
		// roster by shift must not recolour anyone.
		expect(avatarClass('01J8ZK')).toBe(avatarClass('01J8ZK'));
		expect(avatarClass(null)).toBe('bg-muted');
	});
});

describe('impliedWorkState', () => {
	it('claims an untouched ticket and releases a merely-assigned one', () => {
		expect(impliedWorkState('unassigned', 'op-1')).toBe('assigned');
		expect(impliedWorkState('assigned', null)).toBe('unassigned');
	});

	it('never disturbs work that is already under way', () => {
		// Reassigning in-progress or blocked work must not quietly reset it —
		// this mirrors the guard in app/assignments/service.py.
		expect(impliedWorkState('in_progress', 'op-2')).toBe('in_progress');
		expect(impliedWorkState('blocked', 'op-2')).toBe('blocked');
		expect(impliedWorkState('in_progress', null)).toBe('in_progress');
		expect(impliedWorkState('resolved', 'op-2')).toBe('resolved');
	});
});
