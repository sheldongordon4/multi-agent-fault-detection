import { create } from 'zustand';
import {
	createJSONStorage,
	devtools,
	persist,
	subscribeWithSelector,
} from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import {
	createIncidentsSlice,
	type IncidentsSlice,
} from '@features/incidents/store/incident-slice';
import {
	createOverviewSlice,
	type OverviewSlice,
} from '@features/overview/store/overview-slice';
import {
	applyTheme,
	createThemeSlice,
	type ThemeSlice,
} from './slices/theme-slice';

// The root store composes per-feature UI slices (local UI state only; server
// data lives in react-query). MAFD has no auth, so there is no auth slice.
export type StoreState = ThemeSlice & IncidentsSlice & OverviewSlice;

export const useStore = create<StoreState>()(
	subscribeWithSelector(
		devtools(
			persist(
				immer((...args) => ({
					...createThemeSlice(...args),
					...createIncidentsSlice(...args),
					...createOverviewSlice(...args),
				})),
				{
					name: 'mafd-store',
					storage: createJSONStorage(() => localStorage),
					onRehydrateStorage: () => (state) => {
						applyTheme(state?.theme ?? 'system');
					},
					partialize: (state) => ({
						theme: state.theme,
						language: state.language,
						incidentSeverity: state.incidentSeverity,
						incidentStatus: state.incidentStatus,
						selectedBusId: state.selectedBusId,
						signalMetric: state.signalMetric,
					}),
				}
			),
			{ name: 'MAFDDevtools' }
		)
	)
);
