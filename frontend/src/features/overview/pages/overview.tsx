import { useEffect, useMemo } from 'react';
import { Link } from 'react-router';
import { ArrowRight } from 'lucide-react';
import { useStore } from '@app/store';
import { Button } from '@shared/components/ui/button';
import { useFetchIncidents } from '@features/incidents/hooks/use-fetch-incidents';
import { RepeatOffendersCard } from '@features/insights/components/repeat-offenders-card';
import { FaultTypeChart } from '../components/fault-type-chart';
import { summariseIncidents } from '../utils/helpers';
import { LiveSignalChart } from '../components/live-signal-chart';
import { StatTiles } from '../components/stat-tiles';
import { useFetchSignalBuses } from '../hooks/use-fetch-signal-buses';
import { useSignalStream } from '../hooks/use-signal-stream';

export default function Overview() {
	const selectedBusId = useStore((state) => state.selectedBusId);
	const setSelectedBusId = useStore((state) => state.setSelectedBusId);
	const signalMetric = useStore((state) => state.signalMetric);
	const setSignalMetric = useStore((state) => state.setSignalMetric);

	const { incidents, isPending } = useFetchIncidents();
	const { buses, isPending: busesPending } = useFetchSignalBuses();
	const { readings, status } = useSignalStream(selectedBusId);

	// Buses are discovered from live traffic, so the selection has to reconcile
	// with whatever the server reports: pick the first bus once one appears, and
	// drop a persisted selection that is no longer streaming.
	useEffect(() => {
		if (buses.length === 0) return;
		if (!selectedBusId || !buses.includes(selectedBusId)) {
			setSelectedBusId(buses[0]);
		}
	}, [buses, selectedBusId, setSelectedBusId]);

	const counts = useMemo(() => summariseIncidents(incidents), [incidents]);

	return (
		<div className="w-full space-y-4 p-4 md:p-6">
			<header className="flex flex-wrap items-end justify-between gap-3">
				<div>
					<h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
					<p className="text-muted-foreground mt-1 text-sm">
						Pipeline activity and the live per-bus signal feed.
					</p>
				</div>

				<Button asChild variant="outline" size="sm" className="gap-1.5">
					<Link to="/incidents">
						All incidents
						<ArrowRight className="size-3.5" />
					</Link>
				</Button>
			</header>

			<StatTiles
				total={counts.total}
				high={counts.high}
				medium={counts.medium}
				low={counts.low}
				customersAffected={counts.customersAffected}
				isPending={isPending}
			/>

			{/* The bus selector lives on the chart, not in the page header: it only
			    ever changed the chart, and from the header it read as a page-wide
			    filter the stat tiles and fault-type chart don't honour. */}
			<LiveSignalChart
				readings={readings}
				status={status}
				metric={signalMetric}
				onMetricChange={setSignalMetric}
				busId={selectedBusId}
				buses={buses}
				onBusChange={setSelectedBusId}
				busesPending={busesPending}
			/>

			<div className="grid gap-4 xl:grid-cols-2">
				<FaultTypeChart incidents={incidents} />
				<RepeatOffendersCard />
			</div>
		</div>
	);
}
