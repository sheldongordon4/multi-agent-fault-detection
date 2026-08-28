import { Activity, ShieldAlert, TriangleAlert, Waves } from 'lucide-react';
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
	isPending,
}: {
	total: number;
	high: number;
	medium: number;
	low: number;
	isPending: boolean;
}) {
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
		</div>
	);
}
