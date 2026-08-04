import type { StateCreator } from 'zustand';
import type { StoreState } from '../../../app/store/index';
import type { Severity, TicketStatus } from '../../../shared/types';

export type SeverityFilter = Severity | 'all';
export type StatusFilter = TicketStatus | 'all';

export type IncidentsSliceState = {
	incidentSearch: string;
	incidentSeverity: SeverityFilter;
	incidentStatus: StatusFilter;
};

export type IncidentsSliceActions = {
	setIncidentSearch: (query: string) => void;
	setIncidentSeverity: (severity: SeverityFilter) => void;
	setIncidentStatus: (status: StatusFilter) => void;
	resetIncidentFilters: () => void;
};

export type IncidentsSlice = IncidentsSliceState & IncidentsSliceActions;

const initialState: IncidentsSliceState = {
	incidentSearch: '',
	incidentSeverity: 'all',
	incidentStatus: 'all',
};

// Local UI state only — the tickets themselves live in react-query. The selected
// incident is NOT stored here: the URL (/incidents/:incidentId) is the source of
// truth for selection.
export const createIncidentsSlice: StateCreator<
	StoreState,
	[],
	[],
	IncidentsSlice
> = (set) => ({
	...initialState,
	setIncidentSearch: (query) => set({ incidentSearch: query }),
	setIncidentSeverity: (severity) => set({ incidentSeverity: severity }),
	setIncidentStatus: (status) => set({ incidentStatus: status }),
	resetIncidentFilters: () => set({ ...initialState }),
});
