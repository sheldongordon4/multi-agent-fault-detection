import type { Assignment, OperatorRole, Priority, WorkState } from '@shared/types';

export const WORK_STATE_LABELS: Record<WorkState, string> = {
	unassigned: 'Unassigned',
	assigned: 'Assigned',
	in_progress: 'In progress',
	blocked: 'Blocked',
	resolved: 'Resolved',
	closed: 'Closed',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
	p1: 'P1',
	p2: 'P2',
	p3: 'P3',
	p4: 'P4',
};

export const ROLE_LABELS: Record<OperatorRole, string> = {
	control_room: 'Control room',
	field_crew: 'Field crew',
	protection_eng: 'Protection eng',
	supervisor: 'Supervisor',
};

/** States that no longer count as open work (mirrors TERMINAL_STATES server-side). */
const TERMINAL_STATES = new Set<WorkState>(['resolved', 'closed']);

export function isTerminal(state: WorkState): boolean {
	return TERMINAL_STATES.has(state);
}

export function workStateLabel(state: WorkState | string): string {
	return WORK_STATE_LABELS[state as WorkState] ?? String(state);
}

/**
 * Stable colour per operator so the same person is the same colour everywhere.
 * Hashed from the id rather than the list index, which would reshuffle whenever
 * the roster is reordered by shift.
 */
const AVATAR_CLASSES = [
	'bg-chart-1',
	'bg-chart-2',
	'bg-chart-3',
	'bg-chart-4',
	'bg-chart-5',
];

export function avatarClass(operatorId: string | null | undefined): string {
	if (!operatorId) return 'bg-muted';
	let hash = 0;
	for (let i = 0; i < operatorId.length; i += 1) {
		hash = (hash * 31 + operatorId.charCodeAt(i)) | 0;
	}
	return AVATAR_CLASSES[Math.abs(hash) % AVATAR_CLASSES.length];
}

export function initialsOf(name: string | null | undefined): string {
	const text = (name ?? '').trim();
	if (!text) return '—';
	const parts = text.split(/\s+/);
	if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
	return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Compact age, e.g. "3m", "1h 12m", "2d". Operators scan this, so keep it short. */
export function formatAge(iso: string | null | undefined, now: number = Date.now()): string {
	if (!iso) return '—';
	const then = new Date(iso).getTime();
	if (Number.isNaN(then)) return '—';

	const minutes = Math.max(0, Math.floor((now - then) / 60000));
	if (minutes < 60) return `${minutes}m`;

	const hours = Math.floor(minutes / 60);
	if (hours < 24) {
		const rest = minutes % 60;
		return rest ? `${hours}h ${String(rest).padStart(2, '0')}m` : `${hours}h`;
	}
	return `${Math.floor(hours / 24)}d`;
}

export type SlaState = 'none' | 'paused' | 'met' | 'over' | 'due';

export interface SlaReading {
	state: SlaState;
	label: string;
}

/**
 * The SLA clock is derived from `due_at`, never stored as a countdown.
 *
 * Blocked work reads "paused": a clock that keeps running while a transformer
 * waits on a lab result is measuring the lab, not the operator.
 */
export function readSla(assignment: Assignment, now: number = Date.now()): SlaReading {
	if (!assignment.due_at) return { state: 'none', label: '—' };

	if (assignment.work_state === 'blocked') {
		return { state: 'paused', label: 'paused' };
	}

	if (isTerminal(assignment.work_state)) {
		return { state: 'met', label: 'met' };
	}

	const due = new Date(assignment.due_at).getTime();
	if (Number.isNaN(due)) return { state: 'none', label: '—' };

	const minutes = Math.round((due - now) / 60000);
	if (minutes < 0) return { state: 'over', label: `${formatMinutes(-minutes)} over` };
	return { state: 'due', label: `${formatMinutes(minutes)} left` };
}

function formatMinutes(minutes: number): string {
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.floor(minutes / 60);
	const rest = minutes % 60;
	if (hours < 24) return rest ? `${hours}h ${String(rest).padStart(2, '0')}m` : `${hours}h`;
	return `${Math.floor(hours / 24)}d`;
}

/**
 * The work state a (re)assignment implies, mirroring `update_assignment` in
 * app/assignments/service.py.
 *
 * The server is authoritative — this exists only so the optimistic row doesn't
 * flash the old state before the response lands. Keep the two in step: if the
 * server's rule changes, this changes with it.
 */
export function impliedWorkState(
	current: WorkState,
	operatorId: string | null
): WorkState {
	if (operatorId && current === 'unassigned') return 'assigned';
	if (!operatorId && current === 'assigned') return 'unassigned';
	return current;
}
