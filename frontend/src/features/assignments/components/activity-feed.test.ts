import { describe, expect, it } from 'vitest';
import type { AssignmentEvent } from '@shared/types';
import { describeEvent } from './activity-feed';

const base: AssignmentEvent = {
	id: '01J8',
	incident_id: 'ieee13:b671:1',
	actor_id: 'op-1',
	actor_name: 'K. Reid',
	kind: 'commented',
	from_value: null,
	to_value: null,
	body: null,
	created_at: '2026-09-05T12:00:00Z',
};

describe('describeEvent', () => {
	it('resolves enum values to the labels shown everywhere else', () => {
		// The log stores raw values; rendering `in_progress` verbatim would make
		// the feed read like a database dump.
		expect(
			describeEvent({ ...base, kind: 'state_changed', to_value: 'in_progress' })
		).toBe('K. Reid moved this to In progress');

		expect(
			describeEvent({ ...base, kind: 'priority_changed', to_value: 'p1' })
		).toBe('K. Reid set priority to P1');
	});

	it('names the system when no operator was claimed', () => {
		// An unattributed event is the honest outcome of MAFD having no auth —
		// it must not silently read as though someone did it.
		expect(
			describeEvent({ ...base, kind: 'assigned', actor_id: null, actor_name: null })
		).toBe('The system assigned this ticket');
	});

	it('distinguishes updating a note from clearing one', () => {
		expect(describeEvent({ ...base, kind: 'note_changed', body: 'Crew en route' })).toBe(
			'K. Reid updated the disposition note'
		);
		expect(describeEvent({ ...base, kind: 'note_changed', body: null })).toBe(
			'K. Reid cleared the disposition note'
		);
	});

	it('falls back rather than rendering nothing for an unknown kind', () => {
		expect(
			describeEvent({ ...base, kind: 'teleported' as AssignmentEvent['kind'] })
		).toBe('K. Reid updated this ticket');
	});
});
