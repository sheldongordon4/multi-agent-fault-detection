import { useEffect, useMemo } from 'react';
import { Link } from 'react-router';
import { ArrowRight } from 'lucide-react';
import { useStore } from '../../../app/store';
import { Button } from '../../../shared/components/ui/button';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '../../../shared/components/ui/select';
import { useFetchIncidents } from '../../incidents/hooks/use-fetch-incidents';
import { normalizeSeverity } from '../../incidents/utils/helpers';
import { FaultTypeChart } from '../components/fault-type-chart';
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

	const counts = useMemo(() => {
		let high = 0;
		let medium = 0;
		let low = 0;

		for (const incident of incidents) {
			const severity = normalizeSeverity(incident.severity);
			if (severity === 'high') high += 1;
			else if (severity === 'medium') medium += 1;
			else low += 1;
		}

		return { total: incidents.length, high, medium, low };
	}, [incidents]);

	return (
		<div className="mx-auto w-full max-w-7xl space-y-4 p-4 md:p-6">
			<header className="flex flex-wrap items-end justify-between gap-3">
				<div>
					<h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
					<p className="text-muted-foreground mt-1 text-sm">
						Pipeline activity and the live per-bus signal feed.
					</p>
				</div>

				<div className="flex items-center gap-2">
					<Select
						value={selectedBusId ?? ''}
						onValueChange={setSelectedBusId}
						disabled={buses.length === 0}
					>
						<SelectTrigger className="h-9 w-40 text-xs" aria-label="Select bus">
							<SelectValue
								placeholder={busesPending ? 'Loading buses…' : 'No buses live'}
							/>
						</SelectTrigger>
						<SelectContent>
							{buses.map((bus) => (
								<SelectItem key={bus} value={bus} className="font-mono">
									{bus}
								</SelectItem>
							))}
						</SelectContent>
					</Select>

					<Button asChild variant="outline" size="sm" className="gap-1.5">
						<Link to="/incidents">
							All incidents
							<ArrowRight className="size-3.5" />
						</Link>
					</Button>
				</div>
			</header>

			<StatTiles
				total={counts.total}
				high={counts.high}
				medium={counts.medium}
				low={counts.low}
				isPending={isPending}
			/>

			<LiveSignalChart
				readings={readings}
				status={status}
				metric={signalMetric}
				onMetricChange={setSignalMetric}
				busId={selectedBusId}
			/>

			<FaultTypeChart incidents={incidents} />
		</div>
	);
}
