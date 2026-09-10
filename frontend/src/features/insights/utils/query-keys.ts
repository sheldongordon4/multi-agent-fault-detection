export const insightQueryKeys = {
	all: ['insights'] as const,
	repeatOffenders: (days: number, minOccurrences: number) =>
		[...insightQueryKeys.all, 'repeat-offenders', days, minOccurrences] as const,
};
