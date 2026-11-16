import { useMemo } from 'react';
import {
	Bar,
	BarChart,
	CartesianGrid,
	Cell,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import type { TicketSummary } from '@shared/types';
import {
	faultTypeInfo,
	formatFaultCode,
	normalizeSeverity,
} from '@features/incidents/utils/helpers';

const severityColor: Record<string, string> = {
	high: 'var(--destructive)',
	medium: 'var(--warning)',
	low: 'var(--success)',
};


type Datum = { code: string; count: number; worst: string };

/**
 * What the bar actually means.
 *
 * `SLG` and `OPEN_2PH` are unreadable unless you already know them, so the
 * tooltip leads with the full name, says what physically happened, and names the
 * signature the classifier keyed on. The last part is the useful one: it answers
 * "why did it decide that", which a bare count never does.
 */
function FaultTooltip({
	active,
	payload,
}: {
	active?: boolean;
	payload?: { payload: Datum }[];
}) {
	if (!active || !payload?.length) return null;

	const datum = payload[0].payload;
	const info = faultTypeInfo(datum.code);

	return (
		<div className="border-border bg-popover text-popover-foreground max-w-[280px] rounded-md border p-3 shadow-md">
			<div className="flex items-baseline gap-2">
				<span className="font-mono text-xs font-semibold">{datum.code}</span>
				<span className="text-muted-foreground text-[11px] tracking-wide uppercase">
					{severityLabel[datum.worst] ?? datum.worst}
				</span>
				<span className="ml-auto font-mono text-sm font-semibold tabular-nums">
					{datum.count}
				</span>
			</div>

			<p className="mt-1 text-sm font-medium">{info.name}</p>
			<p className="text-muted-foreground mt-1 text-xs leading-5">
				{info.description}
			</p>

			<p className="border-border/60 text-muted-foreground mt-2 border-t pt-2 text-[11px] leading-4 italic">
				{info.signature}
			</p>
		</div>
	);
}

const severityLabel: Record<string, string> = {
	high: 'worst: high',
	medium: 'worst: medium',
	low: 'worst: low',
};

/**
 * Fault-type distribution across the loaded tickets. Each bar is coloured by the
 * worst severity seen for that fault code, so a tall amber bar and a short red
 * one read differently at a glance.
 */
export function FaultTypeChart({ incidents }: { incidents: TicketSummary[] }) {
	const data = useMemo(() => {
		const buckets = new Map<string, { count: number; worst: string }>();
		const rank: Record<string, number> = { low: 1, medium: 2, high: 3 };

		for (const incident of incidents) {
			const code = formatFaultCode(incident.fault_type);
			const severity = normalizeSeverity(incident.severity);
			const existing = buckets.get(code);

			if (!existing) {
				buckets.set(code, { count: 1, worst: severity });
				continue;
			}

			existing.count += 1;
			if ((rank[severity] ?? 0) > (rank[existing.worst] ?? 0)) {
				existing.worst = severity;
			}
		}

		return [...buckets.entries()]
			.map(([code, { count, worst }]) => ({ code, count, worst }))
			.sort((a, b) => b.count - a.count)
			.slice(0, 8);
	}, [incidents]);

	return (
		<section className="border-border/60 bg-card rounded-lg border">
			<header className="border-border/60 flex items-center gap-2 border-b px-4 py-3">
				<BarChart3 className="text-muted-foreground size-4" />
				<h2 className="text-sm font-semibold">Fault types</h2>
				<span className="text-muted-foreground ml-auto font-mono text-xs">
					{incidents.length} tickets
				</span>
			</header>

			<div className="h-72 p-4">
				{data.length === 0 ? (
					<div className="text-muted-foreground flex h-full items-center justify-center text-sm">
						No fault tickets yet.
					</div>
				) : (
					<ResponsiveContainer width="100%" height="100%">
						<BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
							<CartesianGrid
								strokeDasharray="3 3"
								stroke="var(--border)"
								vertical={false}
							/>
							<XAxis
								dataKey="code"
								stroke="var(--muted-foreground)"
								tick={{ fontSize: 11 }}
								tickLine={false}
								axisLine={false}
							/>
							<YAxis
								stroke="var(--muted-foreground)"
								tick={{ fontSize: 11 }}
								tickLine={false}
								axisLine={false}
								allowDecimals={false}
								width={40}
							/>
							<Tooltip
								cursor={{ fill: 'var(--accent)', opacity: 0.4 }}
								content={<FaultTooltip />}
								// Codes are short and the descriptions are not, so the default
								// hug-the-cursor placement would push the panel off the right
								// edge on the last few bars.
								wrapperStyle={{ outline: 'none' }}
							/>
							<Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
								{data.map((entry) => (
									<Cell
										key={entry.code}
										fill={severityColor[entry.worst] ?? 'var(--primary)'}
									/>
								))}
							</Bar>
						</BarChart>
					</ResponsiveContainer>
				)}
			</div>
		</section>
	);
}
