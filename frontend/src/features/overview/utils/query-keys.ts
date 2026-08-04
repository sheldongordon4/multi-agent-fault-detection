export const signalQueryKeys = {
	all: ['signals'] as const,
	buses: () => [...signalQueryKeys.all, 'buses'] as const,
};
