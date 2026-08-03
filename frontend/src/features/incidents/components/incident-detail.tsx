import {
	AlertCircle,
	BookText,
	ClipboardList,
	ExternalLink,
	MousePointerClick,
	RefreshCw,
	Waves,
} from 'lucide-react';
import { Button } from '../../../shared/components/ui/button';
import {
	Empty,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from '../../../shared/components/ui/empty';
import { ScrollArea } from '../../../shared/components/ui/scroll-area';
import { Separator } from '../../../shared/components/ui/separator';
import { Skeleton } from '../../../shared/components/ui/skeleton';
import type {
	EvidenceWindow,
	KBCitation,
	TicketDetail,
} from '../../../shared/types';
import { formatFaultType, formatTimestamp } from '../utils/helpers';
import { SeverityBadge, StatusBadge } from './severity-badge';

function Field({ label, value }: { label: string; value: string }) {
	return (
		<div className="min-w-0">
			<p className="text-muted-foreground text-[11px] tracking-wide uppercase">
				{label}
			</p>
			<p className="mt-0.5 truncate font-mono text-sm" title={value}>
				{value}
			</p>
		</div>
	);
}

function Section({
	icon: Icon,
	title,
	children,
}: {
	icon: typeof BookText;
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section className="px-5 py-4">
			<h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
				<Icon className="text-muted-foreground size-4" />
				{title}
			</h3>
			{children}
		</section>
	);
}

export function IncidentDetailSkeleton() {
	return (
		<div className="p-5" aria-busy="true" aria-label="Loading incident">
			<Skeleton className="h-7 w-56" />
			<Skeleton className="mt-2 h-4 w-40" />
			<div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
				{Array.from({ length: 4 }).map((_, i) => (
					<Skeleton key={i} className="h-10" />
				))}
			</div>
			<Skeleton className="mt-6 h-24 w-full" />
			<Skeleton className="mt-4 h-32 w-full" />
		</div>
	);
}

export function IncidentDetailEmpty() {
	return (
		<div className="flex h-full items-center justify-center p-8">
			<Empty className="border-none">
				<EmptyHeader>
					<EmptyMedia variant="icon">
						<MousePointerClick className="text-muted-foreground" />
					</EmptyMedia>
					<EmptyTitle>No incident selected</EmptyTitle>
					<EmptyDescription>
						Pick a fault ticket from the list to see its root cause, recommended
						actions, evidence, and the SOP citations behind them.
					</EmptyDescription>
				</EmptyHeader>
			</Empty>
		</div>
	);
}

export function IncidentDetailError({ onRetry }: { onRetry: () => void }) {
	return (
		<div className="flex h-full items-center justify-center p-8">
			<Empty className="border-none">
				<EmptyHeader>
					<EmptyMedia variant="icon">
						<AlertCircle className="text-destructive" />
					</EmptyMedia>
					<EmptyTitle>Couldn't load this ticket</EmptyTitle>
					<EmptyDescription>
						The ticket may not exist yet, or the API is unreachable.
					</EmptyDescription>
				</EmptyHeader>
				<Button variant="outline" size="sm" onClick={onRetry} className="gap-2">
					<RefreshCw className="size-3.5" />
					Try again
				</Button>
			</Empty>
		</div>
	);
}

export function IncidentDetail({ incident }: { incident: TicketDetail }) {
	// The full coordinator output lives in `raw`; the columns are a thin
	// projection. Every raw field is optional — narrow before rendering.
	const raw = incident.raw ?? {};
	const rootCause = typeof raw.root_cause === 'string' ? raw.root_cause : null;
	const summary = incident.summary ?? (typeof raw.summary === 'string' ? raw.summary : null);
	const actions = Array.isArray(raw.recommended_actions)
		? (raw.recommended_actions as string[])
		: [];
	const evidence = Array.isArray(raw.evidence)
		? (raw.evidence as EvidenceWindow[])
		: [];
	const citations = Array.isArray(raw.kb_citations)
		? (raw.kb_citations as KBCitation[])
		: [];

	return (
		<ScrollArea className="h-full">
			<header className="border-border/60 border-b px-5 py-4">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="text-xl font-semibold tracking-tight">
						{incident.bus_id ?? 'Unknown bus'}
					</h2>
					<SeverityBadge severity={incident.severity} />
					<StatusBadge status={incident.status} />
				</div>
				<p className="text-muted-foreground mt-1 font-mono text-xs">
					{incident.incident_id}
				</p>

				<div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
					<Field label="Fault type" value={formatFaultType(incident.fault_type)} />
					<Field label="Scenario" value={incident.scenario ?? '—'} />
					<Field label="Ticket" value={incident.ticket_id} />
					<Field label="Detected" value={formatTimestamp(incident.created_at)} />
				</div>
			</header>

			{summary && (
				<>
					<Section icon={ClipboardList} title="Summary">
						<p className="text-sm leading-6">{summary}</p>
					</Section>
					<Separator />
				</>
			)}

			{rootCause && (
				<>
					<Section icon={AlertCircle} title="Root cause">
						<p className="text-sm leading-6">{rootCause}</p>
					</Section>
					<Separator />
				</>
			)}

			{actions.length > 0 && (
				<>
					<Section icon={ClipboardList} title="Recommended actions">
						<ol className="space-y-2">
							{actions.map((action, index) => (
								<li key={index} className="flex gap-3 text-sm leading-6">
									<span className="bg-muted text-muted-foreground mt-0.5 flex size-5 shrink-0 items-center justify-center rounded font-mono text-[11px]">
										{index + 1}
									</span>
									<span>{action}</span>
								</li>
							))}
						</ol>
					</Section>
					<Separator />
				</>
			)}

			{evidence.length > 0 && (
				<>
					<Section icon={Waves} title="Evidence">
						<div className="space-y-2">
							{evidence.map((window, index) => (
								<div
									key={index}
									className="border-border/60 bg-muted/30 rounded-md border p-3"
								>
									<div className="flex items-center justify-between gap-2">
										<span className="font-mono text-xs font-medium">
											{window.metric}
										</span>
										<span className="text-muted-foreground font-mono text-[11px]">
											{formatTimestamp(window.start_timestamp)} →{' '}
											{formatTimestamp(window.end_timestamp)}
										</span>
									</div>
									{window.description && (
										<p className="text-muted-foreground mt-1.5 text-xs leading-5">
											{window.description}
										</p>
									)}
								</div>
							))}
						</div>
					</Section>
					<Separator />
				</>
			)}

			{citations.length > 0 && (
				<Section icon={BookText} title="SOP citations">
					<div className="space-y-2">
						{citations.map((citation, index) => (
							<div
								key={index}
								className="border-border/60 rounded-md border p-3"
							>
								<div className="flex items-start justify-between gap-2">
									<div className="min-w-0">
										<p className="truncate text-sm font-medium">
											{citation.title}
										</p>
										<p className="text-muted-foreground mt-0.5 font-mono text-[11px]">
											{citation.source_id}
											{citation.section ? ` · ${citation.section}` : ''}
										</p>
									</div>
									{citation.url && (
										<a
											href={citation.url}
											target="_blank"
											rel="noopener noreferrer"
											className="text-muted-foreground hover:text-foreground shrink-0"
											aria-label={`Open ${citation.title}`}
										>
											<ExternalLink className="size-4" />
										</a>
									)}
								</div>
								{citation.snippet && (
									<p className="text-muted-foreground border-border/60 mt-2 border-l-2 pl-3 text-xs leading-5 italic">
										{citation.snippet}
									</p>
								)}
							</div>
						))}
					</div>
				</Section>
			)}
		</ScrollArea>
	);
}
