import { useMemo } from 'react';
import { useParams } from 'react-router';
import { useStore } from '../../../app/store';
import {
	IncidentDetail,
	IncidentDetailEmpty,
	IncidentDetailError,
	IncidentDetailSkeleton,
} from '../components/incident-detail';
import { IncidentFilters } from '../components/incident-filters';
import { IncidentList } from '../components/incident-list';
import { useFetchIncident } from '../hooks/use-fetch-incident';
import { useFetchIncidents } from '../hooks/use-fetch-incidents';
import { filterIncidents } from '../utils/helpers';

export default function Incidents() {
	// The URL owns selection so a ticket is deep-linkable and the back button works.
	const { incidentId } = useParams<{ incidentId: string }>();
	const selectedIncidentId = incidentId ?? null;

	const search = useStore((state) => state.incidentSearch);
	const severity = useStore((state) => state.incidentSeverity);
	const status = useStore((state) => state.incidentStatus);

	const {
		incidents,
		isPending: listPending,
		isError: listError,
		refetch: refetchList,
	} = useFetchIncidents();

	const {
		incident,
		isPending: detailPending,
		isError: detailError,
		refetch: refetchDetail,
	} = useFetchIncident(selectedIncidentId);

	const visibleIncidents = useMemo(
		() => filterIncidents(incidents, { search, severity, status }),
		[incidents, search, severity, status]
	);

	const hasFilters =
		search.trim() !== '' || severity !== 'all' || status !== 'all';

	const renderDetail = () => {
		if (!selectedIncidentId) return <IncidentDetailEmpty />;
		if (detailPending) return <IncidentDetailSkeleton />;
		if (detailError || !incident) {
			return <IncidentDetailError onRetry={() => void refetchDetail()} />;
		}
		return <IncidentDetail incident={incident} />;
	};

	return (
		<div className="flex h-full min-h-0">
			<aside className="border-border/60 flex w-full max-w-sm min-w-0 flex-col border-r md:w-80 lg:w-96">
				<IncidentFilters resultCount={visibleIncidents.length} />
				<IncidentList
					incidents={visibleIncidents}
					selectedIncidentId={selectedIncidentId}
					isPending={listPending}
					isError={listError}
					onRetry={() => void refetchList()}
					hasFilters={hasFilters}
				/>
			</aside>

			<main className="min-w-0 flex-1">{renderDetail()}</main>
		</div>
	);
}
