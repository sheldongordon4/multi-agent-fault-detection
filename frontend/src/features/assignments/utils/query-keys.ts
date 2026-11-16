import type { AssignmentFilters } from '../store/assignment-slice';

export const assignmentQueryKeys = {
	all: ['assignments'] as const,
	list: (filters: AssignmentFilters) =>
		[...assignmentQueryKeys.all, 'list', filters] as const,
	detail: (incidentId: string) =>
		[...assignmentQueryKeys.all, 'detail', incidentId] as const,
	events: (incidentId: string) =>
		[...assignmentQueryKeys.all, 'events', incidentId] as const,
};

export const operatorQueryKeys = {
	all: ['operators'] as const,
	list: () => [...operatorQueryKeys.all, 'list'] as const,
};
