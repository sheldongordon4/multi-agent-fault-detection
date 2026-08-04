export const incidentQueryKeys = {
	all: ['incidents'] as const,
	list: (limit: number) => [...incidentQueryKeys.all, 'list', limit] as const,
	detail: (incidentId: string) =>
		[...incidentQueryKeys.all, 'detail', incidentId] as const,
};
