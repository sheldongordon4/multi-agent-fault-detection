import { cn } from '@shared/lib/utils';
import type { Severity, TicketStatus } from '@shared/types';
import { normalizeSeverity, normalizeStatus } from '../utils/helpers';

const severityStyles: Record<Severity, string> = {
	high: 'border-destructive/40 bg-destructive/12 text-destructive',
	medium: 'border-warning/40 bg-warning/12 text-warning',
	low: 'border-success/40 bg-success/12 text-success',
};

/**
 * Severity is the primary scan signal in the list, so it gets a solid dot plus
 * a tinted chip rather than relying on text color alone (color is never the only
 * carrier — the label is always present).
 */
export function SeverityBadge({
	severity,
	className,
	showDot = true,
}: {
	severity: string | null | undefined;
	className?: string;
	showDot?: boolean;
}) {
	const level = normalizeSeverity(severity);

	return (
		<span
			className={cn(
				'inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide',
				severityStyles[level],
				className
			)}
		>
			{showDot && (
				<span className="size-1.5 rounded-full bg-current" aria-hidden />
			)}
			{level}
		</span>
	);
}

const statusStyles: Record<TicketStatus, string> = {
	diagnosed: 'border-primary/40 bg-primary/10 text-primary',
	acknowledged: 'border-border bg-muted text-muted-foreground',
	resolved: 'border-success/40 bg-success/10 text-success',
};

export function StatusBadge({
	status,
	className,
}: {
	status: string | null | undefined;
	className?: string;
}) {
	const value = normalizeStatus(status);

	return (
		<span
			className={cn(
				'inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium',
				statusStyles[value],
				className
			)}
		>
			{value}
		</span>
	);
}
