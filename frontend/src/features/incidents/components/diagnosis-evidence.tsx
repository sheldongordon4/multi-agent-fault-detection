import { Gauge, ScanSearch, Users } from 'lucide-react';
import { Progress } from '@shared/components/ui/progress';
import type {
	ClassifierAlternative,
	FeatureAttribution,
} from '@shared/types';
import { faultTypeInfo } from '../utils/helpers';

/**
 * The measured half of a diagnosis: how sure the classifier was, what put the
 * event outside normal, and how many customers it costs.
 *
 * These three come from the pipeline rather than from the coordinator's prose
 * (app/faults/service.py::_enrich_ticket), which is the point of showing them
 * apart from the summary. A generated paragraph can say anything; a sigma
 * against the training baseline is checkable against a meter.
 */

/** Below this the classifier is guessing between neighbours, and should say so. */
const LOW_CONFIDENCE = 0.75;

function confidenceTone(value: number): string {
	if (value >= 0.9) return 'text-emerald-600 dark:text-emerald-400';
	if (value >= LOW_CONFIDENCE) return 'text-amber-600 dark:text-amber-400';
	return 'text-rose-600 dark:text-rose-400';
}

export function ClassifierConfidence({
	faultType,
	confidence,
	alternatives = [],
}: {
	faultType: string | null;
	confidence: number;
	alternatives?: ClassifierAlternative[];
}) {
	const pct = Math.round(confidence * 100);
	const runnersUp = alternatives.filter((a) => a.confidence > 0.005);
	const info = faultTypeInfo(faultType);

	return (
		<div className="space-y-3">
			<div className="flex items-baseline justify-between gap-3">
				<span className="text-sm font-medium">{info.name}</span>
				<span className={`font-mono text-lg font-semibold ${confidenceTone(confidence)}`}>
					{pct}%
				</span>
			</div>

			<Progress value={pct} className="h-1.5" />

			{runnersUp.length > 0 && (
				<div className="space-y-1">
					<p className="text-muted-foreground text-xs">Also considered</p>
					<ul className="space-y-1">
						{runnersUp.map((alt) => (
							<li
								key={alt.fault_type}
								className="text-muted-foreground flex items-baseline justify-between gap-3 text-xs"
							>
								<span>{faultTypeInfo(alt.fault_type).name}</span>
								<span className="font-mono">{Math.round(alt.confidence * 100)}%</span>
							</li>
						))}
					</ul>
				</div>
			)}

			{confidence < LOW_CONFIDENCE && (
				<p className="text-muted-foreground border-border/60 border-t pt-2 text-xs leading-5">
					The classifier is not confident here. Confirm the fault type against
					the sequence ratios below before dispatching on it.
				</p>
			)}
		</div>
	);
}

export function AttributionList({ items }: { items: FeatureAttribution[] }) {
	return (
		<div className="space-y-2">
			{items.map((item) => (
				<div
					key={item.feature}
					className="border-border/60 bg-muted/30 rounded-md border p-3"
				>
					<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
						<span className="text-sm font-medium">
							{item.label}
							<span className="text-muted-foreground ml-1.5 font-mono text-xs">
								{item.bus}
							</span>
						</span>
						<span className="text-muted-foreground font-mono text-xs">
							{/* Sign carries the meaning: a sag is a collapse, a spike is
							    fault current. Rendering |sigma| would lose that. */}
							{item.sigma > 0 ? '+' : ''}
							{Math.round(item.sigma).toLocaleString()}σ {item.direction} normal
						</span>
					</div>

					<p className="text-muted-foreground mt-1 text-xs leading-5">
						{item.meaning} — measured{' '}
						<span className="text-foreground font-mono">{item.value}</span>{' '}
						against a normal{' '}
						<span className="font-mono">{item.baseline}</span>
					</p>
				</div>
			))}
		</div>
	);
}

export function CustomerImpact({
	customers,
	share,
}: {
	customers: number;
	share?: number | null;
}) {
	return (
		<div className="flex items-baseline gap-3">
			<span className="font-mono text-2xl font-semibold tabular-nums">
				{customers.toLocaleString()}
			</span>
			<span className="text-muted-foreground text-sm">
				customers downstream
				{share != null && ` · ${Math.round(share * 100)}% of the feeder`}
			</span>
		</div>
	);
}

export const DIAGNOSIS_ICONS = { Gauge, ScanSearch, Users };
