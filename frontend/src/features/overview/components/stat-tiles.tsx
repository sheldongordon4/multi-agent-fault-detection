import { Activity, ShieldAlert, TriangleAlert, Users, Waves } from 'lucide-react';
import { cn } from '@shared/lib/utils';
import { Skeleton } from '@shared/components/ui/skeleton';

interface StatTileProps {
	label: string;
	value: string | number;
	hint?: string;
	icon: typeof Activity;
	tone?: 'default' | 'high' | 'medium' | 'success';
	isPending?: boolean;
}

const toneStyles: Record<NonNullable<StatTileProps['tone']>, string> = {
	default: 'text-primary',
	high: 'text-destructive',
	medium: 'text-warning',
	success: 'text-success',
};

export function StatTile({
	label,
	value,
	hint,
	icon: Icon,
	tone = 'default',
	isPending,
}: StatTileProps) {
	return (
		<div className="border-border/60 bg-card rounded-lg border p-4">
			<div className="flex items-center justify-between">
				<p className="text-muted-foreground text-[11px] tracking-wide uppercase">
					{label}
				</p>
				<Icon className={cn('size-4', toneStyles[tone])} />
			</div>

			{isPending ? (
				<Skeleton className="mt-2 h-8 w-16" />
			) : (
				<p
					className={cn(
						'mt-1 font-mono text-3xl leading-tight font-semibold',
						toneStyles[tone]
					)}
				>
					{value}
				</p>
			)}

			{hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
		</div>
	);
}

export function StatTiles({
	total,
	high,
	medium,
	low,
	customersAffected,
	isPending,
}: {
	total: number;
	high: number;
	medium: number;
	low: number;
	/** Null when no open incident sits at a bus with a known customer count. */
	customersAffected: number | null;
	isPending: boolean;
}) {
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
			<StatTile
				label="Total incidents"
				value={total}
				icon={Waves}
				hint="Fault tickets on record"
				isPending={isPending}
			/>
			<StatTile
				label="High severity"
				value={high}
				icon={ShieldAlert}
				tone="high"
				hint="Needs immediate attention"
				isPending={isPending}
			/>
			<StatTile
				label="Medium severity"
				value={medium}
				icon={TriangleAlert}
				tone="medium"
				hint="Monitor and schedule"
				isPending={isPending}
			/>
			<StatTile
				label="Low severity"
				value={low}
				icon={Activity}
				tone="success"
				hint="Informational"
				isPending={isPending}
			/>
			<StatTile
				label="Customers affected"
				// Renders 0 rather than "None", so all five tiles read as one row of
				// counts instead of four numbers and a word. The hint is what says
				// WHICH empty this is — 0 on its own would claim a fault is out
				// there affecting nobody, when the real meaning is that no
				// unresolved incident sits at a bus with a known customer count.
				value={(customersAffected ?? 0).toLocaleString()}
				icon={Users}
				tone={customersAffected ? 'high' : 'default'}
				hint={
					customersAffected
						? 'Downstream of open faults'
						: 'No open fault at a mapped bus'
				}
				isPending={isPending}
			/>
		</div>
	);
}
