import { useMemo } from 'react';
import {
	CartesianGrid,
	Line,
	LineChart,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from 'recharts';
import { Activity, PlugZap, WifiOff } from 'lucide-react';
import { cn } from '@shared/lib/utils';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import type { SignalMetric, SignalReading } from '@shared/types';
import type { SignalConnectionStatus } from '../hooks/use-signal-stream';

export const SIGNAL_METRICS: {
	value: SignalMetric;
	label: string;
	unit: string;
}[] = [
	{ value: 'Va_rms', label: 'Va (RMS)', unit: 'pu' },
	{ value: 'Vb_rms', label: 'Vb (RMS)', unit: 'pu' },
	{ value: 'Vc_rms', label: 'Vc (RMS)', unit: 'pu' },
	{ value: 'Ia_rms', label: 'Ia (RMS)', unit: 'A' },
	{ value: 'Ib_rms', label: 'Ib (RMS)', unit: 'A' },
	{ value: 'Ic_rms', label: 'Ic (RMS)', unit: 'A' },
	// The trigger quantity itself: deepest phase voltage in per unit. A dip
	// below 0.9 here is exactly what wakes the extraction worker.
	{ value: 'v_pu', label: 'Sag (min V)', unit: 'pu' },
];

function StatusPill({ status }: { status: SignalConnectionStatus }) {
	const map: Record<SignalConnectionStatus, { label: string; className: string }> =
		{
			live: { label: 'Live', className: 'text-success border-success/40 bg-success/10' },
			connecting: {
				label: 'Connecting',
				className: 'text-muted-foreground border-border bg-muted',
			},
			error: {
				label: 'Reconnecting',
				className: 'text-warning border-warning/40 bg-warning/10',
			},
		};
	const { label, className } = map[status];

	return (
		<span
			className={cn(
				'inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium',
				className
			)}
		>
			<span
				className={cn(
					'size-1.5 rounded-full bg-current',
					status === 'live' && 'animate-pulse'
				)}
				aria-hidden
			/>
			{label}
		</span>
	);
}

/** HH:MM:SS from the reading timestamp — operators read wall clock, not deltas. */
function formatClock(timestamp: string): string {
	const date = new Date(timestamp.replace(' ', 'T'));
	if (Number.isNaN(date.getTime())) return timestamp;
	return date.toLocaleTimeString(undefined, { hour12: false });
}

interface LiveSignalChartProps {
	readings: SignalReading[];
	status: SignalConnectionStatus;
	metric: SignalMetric;
	onMetricChange: (metric: SignalMetric) => void;
	busId: string | null;
	/** Buses currently publishing to `raw.signals` — discovered from live traffic. */
	buses: string[];
	onBusChange: (busId: string) => void;
	busesPending?: boolean;
}

export function LiveSignalChart({
	readings,
	status,
	metric,
	onMetricChange,
	busId,
	buses,
	onBusChange,
	busesPending = false,
}: LiveSignalChartProps) {
	const active = SIGNAL_METRICS.find((m) => m.value === metric) ?? SIGNAL_METRICS[0];

	const data = useMemo(
		() =>
			readings.map((reading) => ({
				clock: formatClock(reading.timestamp),
				value: reading[metric],
			})),
		[readings, metric]
	);

	return (
		<section className="border-border/60 bg-card rounded-lg border">
			<header className="border-border/60 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
				<div className="flex items-center gap-2">
					<Activity className="text-muted-foreground size-4" />
					<h2 className="text-sm font-semibold">Live signal</h2>
					{busId && <StatusPill status={status} />}
				</div>

				{/* Which bus, then which quantity of it. Both selectors belong to the
				    chart and to nothing else on the page, so they sit on it. */}
				<div className="flex items-center gap-2">
					<Select
						value={busId ?? ''}
						onValueChange={onBusChange}
						disabled={buses.length === 0}
					>
						<SelectTrigger
							className="h-8 w-36 font-mono text-xs"
							aria-label="Select bus"
						>
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

					<Select
						value={metric}
						onValueChange={(value) => onMetricChange(value as SignalMetric)}
					>
						<SelectTrigger className="h-8 w-40 text-xs" aria-label="Signal metric">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{SIGNAL_METRICS.map((option) => (
								<SelectItem key={option.value} value={option.value}>
									{option.label} ({option.unit})
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				</div>
			</header>

			<div className="h-72 p-4">
				{data.length === 0 ? (
					<div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-3 text-center">
						{status === 'error' ? (
							<WifiOff className="size-8" />
						) : (
							<PlugZap className="size-8" />
						)}
						<div>
							<p className="text-sm font-medium">
								{status === 'error'
									? 'Stream unavailable'
									: 'Waiting for readings'}
							</p>
							<p className="mt-1 text-xs">
								Nothing is publishing to{' '}
								<code className="font-mono">raw.signals</code> yet. Run{' '}
								<code className="font-mono">scripts/produce_signals.py</code> to
								drive the feed.
							</p>
						</div>
					</div>
				) : (
					<ResponsiveContainer width="100%" height="100%">
						<LineChart
							data={data}
							margin={{ top: 4, right: 8, bottom: 0, left: -12 }}
						>
							<CartesianGrid
								strokeDasharray="3 3"
								stroke="var(--border)"
								vertical={false}
							/>
							<XAxis
								dataKey="clock"
								stroke="var(--muted-foreground)"
								tick={{ fontSize: 11 }}
								tickLine={false}
								axisLine={false}
								minTickGap={48}
							/>
							<YAxis
								stroke="var(--muted-foreground)"
								tick={{ fontSize: 11 }}
								tickLine={false}
								axisLine={false}
								width={56}
								domain={['auto', 'auto']}
							/>
							<Tooltip
								contentStyle={{
									background: 'var(--popover)',
									border: '1px solid var(--border)',
									borderRadius: 'var(--radius)',
									color: 'var(--popover-foreground)',
									fontSize: 12,
								}}
								labelStyle={{ color: 'var(--muted-foreground)' }}
								formatter={(value) => [
									`${Number(value ?? 0).toFixed(2)} ${active.unit}`,
									active.label,
								]}
							/>
							<Line
								type="monotone"
								dataKey="value"
								stroke="var(--primary)"
								strokeWidth={1.75}
								dot={false}
								// Live data: animating every append causes visible jitter.
								isAnimationActive={false}
							/>
						</LineChart>
					</ResponsiveContainer>
				)}
			</div>
		</section>
	);
}
