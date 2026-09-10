import type { StateCreator } from 'zustand';
import type { StoreState } from '@app/store/index';
import type { Priority, Severity, WorkState } from '@shared/types';

export type WorkStateFilter = WorkState | 'all';
export type AssigneeFilter = string | 'all' | 'unassigned';
export type SeverityFilter = Severity | 'all';
export type PriorityFilter = Priority | 'all';

/** The filter set, shaped so it can be a react-query key directly. */
export type AssignmentFilters = {
	workState: WorkStateFilter;
	assignee: AssigneeFilter;
	severity: SeverityFilter;
	priority: PriorityFilter;
	search: string;
};

export type AssignmentsSliceState = {
	assignmentWorkState: WorkStateFilter;
	assignmentAssignee: AssigneeFilter;
	assignmentSeverity: SeverityFilter;
	assignmentPriority: PriorityFilter;
	assignmentSearch: string;
	/**
	 * Who this terminal is acting as. MAFD has no auth (see AGENTS.md), so this
	 * is a claim, not a credential: it is persisted per browser and sent as
	 * `X-Actor-Id` so the activity log can attribute the change. Null until the
	 * operator picks a name.
	 */
	actingOperatorId: string | null;
};

export type AssignmentsSliceActions = {
	setAssignmentWorkState: (state: WorkStateFilter) => void;
	setAssignmentAssignee: (assignee: AssigneeFilter) => void;
	setAssignmentSeverity: (severity: SeverityFilter) => void;
	setAssignmentPriority: (priority: PriorityFilter) => void;
	setAssignmentSearch: (query: string) => void;
	setActingOperatorId: (operatorId: string | null) => void;
	resetAssignmentFilters: () => void;
};

export type AssignmentsSlice = AssignmentsSliceState & AssignmentsSliceActions;

const initialFilters = {
	assignmentWorkState: 'all' as WorkStateFilter,
	assignmentAssignee: 'all' as AssigneeFilter,
	assignmentSeverity: 'all' as SeverityFilter,
	assignmentPriority: 'all' as PriorityFilter,
	assignmentSearch: '',
};

export const createAssignmentsSlice: StateCreator<
	StoreState,
	[],
	[],
	AssignmentsSlice
> = (set) => ({
	...initialFilters,
	actingOperatorId: null,
	setAssignmentWorkState: (state) => set({ assignmentWorkState: state }),
	setAssignmentAssignee: (assignee) => set({ assignmentAssignee: assignee }),
	setAssignmentSeverity: (severity) => set({ assignmentSeverity: severity }),
	setAssignmentPriority: (priority) => set({ assignmentPriority: priority }),
	setAssignmentSearch: (query) => set({ assignmentSearch: query }),
	setActingOperatorId: (operatorId) => set({ actingOperatorId: operatorId }),
	// Deliberately does not clear `actingOperatorId` — that is who you are, not
	// a filter.
	resetAssignmentFilters: () => set({ ...initialFilters }),
});
