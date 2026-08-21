import type { StateCreator } from 'zustand';
import type { StoreState } from '@app/store/index';
import type { SignalMetric } from '@shared/types';

export type OverviewSliceState = {
	/**
	 * The bus the chart is showing. Null until a bus is picked (or auto-selected
	 * from GET /stream/buses) — the available buses are discovered from live
	 * traffic, never hardcoded.
	 */
	selectedBusId: string | null;
	signalMetric: SignalMetric;
};

export type OverviewSliceActions = {
	setSelectedBusId: (busId: string | null) => void;
	setSignalMetric: (metric: SignalMetric) => void;
};

export type OverviewSlice = OverviewSliceState & OverviewSliceActions;

export const createOverviewSlice: StateCreator<
	StoreState,
	[],
	[],
	OverviewSlice
> = (set) => ({
	selectedBusId: null,
	signalMetric: 'voltage_kv',
	setSelectedBusId: (busId) => set({ selectedBusId: busId }),
	setSignalMetric: (metric) => set({ signalMetric: metric }),
});
