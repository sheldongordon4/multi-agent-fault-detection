import { AlertCircle, ExternalLink, RefreshCw, X } from 'lucide-react';
import { Link } from 'react-router';
import { useStore } from '@app/store';
import { Button } from '@shared/components/ui/button';
import {
	Empty,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from '@shared/components/ui/empty';
import { Label } from '@shared/components/ui/label';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import { Skeleton } from '@shared/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@shared/components/ui/tabs';
import { Textarea } from '@shared/components/ui/textarea';
import {
	IncidentDetail,
	IncidentDetailError,
	IncidentDetailSkeleton,
} from '@features/incidents/components/incident-detail';
import { SeverityBadge } from '@features/incidents/components/severity-badge';
import { useFetchIncident } from '@features/incidents/hooks/use-fetch-incident';
import type { Assignment, Priority, WorkState } from '@shared/types';
import { PRIORITIES, WORK_STATES } from '@shared/types';
import { useFetchAssignment } from '../hooks/use-fetch-assignment';
import { useFetchAssignmentEvents } from '../hooks/use-fetch-assignment-events';
import { useFetchOperators } from '../hooks/use-fetch-operators';
import { useUpdateAssignment } from '../hooks/use-update-assignment';
import type { AssignmentFilters } from '../store/assignment-slice';
import { PRIORITY_LABELS, workStateLabel } from '../utils/helpers';
import { ActivityFeed } from './activity-feed';
import { AssigneePicker } from './assignee-picker';
import { SlaCell } from './assignment-badges';

/**
 * The ticket detail panel, shared by the assignments board and the map.
 *
 * It fetches everything it needs from the incident id alone, so the map page can
 * open it without loading an assignment list it has no other use for. `filters`
 * is passed only by the board, whose list should update optimistically; without
 * it the panel still works and simply refetches.
 *
 * Height comes from the parent — a full-height sheet on the board, a floating
 * card over the map — so nothing here is sized against the viewport.
 */
export function AssignmentDetailPanel({
	incidentId,
	onClose,
	filters,
	showCloseButton = true,
	showMapLink = true,
}: {
	incidentId: string;
	onClose: () => void;
	filters?: AssignmentFilters;
	/** The map page supplies its own close control in the panel chrome. */
	showCloseButton?: boolean;
	/** Suppressed on the map itself, where "view on map" means nothing. */
	showMapLink?: boolean;
}) {
	const actingOperatorId = useStore((state) => state.actingOperatorId);

	const {
		assignment,
		isPending: assignmentPending,
		isError: assignmentError,
		refetch: refetchAssignment,
	} = useFetchAssignment(incidentId);

	const { operators } = useFetchOperators();
	const { mutate, isPending: isMutating } = useUpdateAssignment(filters);

	// The diagnosis half is free: the coordinator's full ticket already has a
	// renderer on the incidents page, and it reads from `raw`, which the
	// assignment projection deliberately does not carry.
	const {
		incident,
		isPending: incidentPending,
		isError: incidentError,
		refetch: refetchIncident,
	} = useFetchIncident(incidentId);

	const { events, isPending: eventsPending } = useFetchAssignmentEvents(incidentId);

	const patch = (
		next: Partial<Assignment>,
		body: Record<string, unknown>
	) => {
		if (!assignment) return;
		mutate({
			incidentId: assignment.incident_id,
			patch: { ...body, expected_version: assignment.version },
			optimistic: next,
		});
	};

	if (assignmentPending) {
		return (
			<div className="space-y-3 p-4" aria-busy="true">
				<Skeleton className="h-6 w-40" />
				<Skeleton className="h-4 w-56" />
				<Skeleton className="h-9 w-full" />
				<Skeleton className="h-24 w-full" />
			</div>
		);
	}

	if (assignmentError || !assignment) {
		return (
			<div className="flex h-full items-center justify-center p-8">
				<Empty className="border-none">
					<EmptyHeader>
						<EmptyMedia variant="icon">
							<AlertCircle className="text-destructive" />
						</EmptyMedia>
						<EmptyTitle>Couldn't load this ticket</EmptyTitle>
						<EmptyDescription>
							It may not exist yet, or the API is unreachable.
						</EmptyDescription>
					</EmptyHeader>
					<Button
						variant="outline"
						size="sm"
						onClick={() => void refetchAssignment()}
						className="gap-2"
					>
						<RefreshCw className="size-3.5" />
						Try again
					</Button>
				</Empty>
			</div>
		);
	}

	return (
		<Tabs defaultValue="work" className="flex h-full min-h-0 flex-col gap-0">
			<header className="border-border/60 shrink-0 border-b px-4 pt-3">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="font-mono text-lg font-medium tracking-tight">
						{assignment.bus_id ?? 'Unknown bus'}
					</h2>
					<SeverityBadge severity={assignment.severity} />

					{showMapLink && (
						<Link
							to={`/incidents/${encodeURIComponent(assignment.incident_id)}`}
							className="text-primary ml-auto inline-flex items-center gap-1 text-xs font-medium hover:underline"
						>
							View on map
							<ExternalLink className="size-3" />
						</Link>
					)}

					{showCloseButton && (
						<Button
							variant="ghost"
							size="icon"
							className="size-7"
							onClick={onClose}
							aria-label="Close detail panel"
						>
							<X className="size-4" />
						</Button>
					)}
				</div>
				<p className="text-muted-foreground mt-1 font-mono text-[11px]">
					{assignment.incident_id}
				</p>

				<TabsList className="mt-3 h-8 bg-transparent p-0">
					<TabsTrigger value="work" className="text-xs">
						Work
					</TabsTrigger>
					<TabsTrigger value="diagnosis" className="text-xs">
						Diagnosis
					</TabsTrigger>
					<TabsTrigger value="activity" className="text-xs">
						Activity
					</TabsTrigger>
				</TabsList>
			</header>

			<TabsContent value="work" className="mt-0 min-h-0 flex-1 overflow-y-auto">
				<div className="flex flex-col gap-4 p-4">
					<div className="flex flex-col gap-1.5">
						<Label className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase">
							Assignee
						</Label>
						<AssigneePicker
							value={assignment.assignee_id}
							operators={operators}
							fallbackName={assignment.assignee_name}
							fallbackInitials={assignment.assignee_initials}
							onChange={(operatorId) => {
								const operator = operators.find((o) => o.id === operatorId);
								patch(
									{
										assignee_id: operatorId,
										assignee_name: operator?.name ?? null,
										assignee_initials: operator?.initials ?? null,
									},
									{ assignee_id: operatorId }
								);
							}}
							disabled={isMutating}
						/>
					</div>

					<div className="grid grid-cols-2 gap-3">
						<div className="flex flex-col gap-1.5">
							<Label className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase">
								State
							</Label>
							<Select
								value={assignment.work_state}
								onValueChange={(next) =>
									patch({ work_state: next as WorkState }, { work_state: next })
								}
								disabled={isMutating}
							>
								<SelectTrigger className="h-8 text-xs" aria-label="Work state">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									{WORK_STATES.map((state) => (
										<SelectItem key={state} value={state}>
											{workStateLabel(state)}
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>

						<div className="flex flex-col gap-1.5">
							<Label className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase">
								Priority
							</Label>
							<Select
								value={assignment.priority}
								onValueChange={(next) =>
									patch({ priority: next as Priority }, { priority: next })
								}
								disabled={isMutating}
							>
								<SelectTrigger className="h-8 text-xs" aria-label="Priority">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									{PRIORITIES.map((level) => (
										<SelectItem key={level} value={level}>
											{PRIORITY_LABELS[level]}
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>
					</div>

					<div className="flex flex-col gap-1.5">
						<Label className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase">
							SLA
						</Label>
						<SlaCell assignment={assignment} className="text-sm" />
					</div>

					<div className="flex flex-col gap-1.5">
						<Label
							htmlFor="disposition-note"
							className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase"
						>
							Disposition note
						</Label>
						<Textarea
							id="disposition-note"
							// Uncontrolled, committed on blur: a controlled field would PATCH
							// on every keystroke, and each PATCH bumps the version and writes
							// an activity event.
							key={`${assignment.incident_id}:${assignment.version}`}
							defaultValue={assignment.note ?? ''}
							onBlur={(e) => {
								const next = e.target.value.trim();
								if (next !== (assignment.note ?? '')) {
									patch({ note: next || null }, { note: next || null });
								}
							}}
							placeholder="What is happening with this ticket right now?"
							className="min-h-[72px] resize-none text-xs"
							disabled={isMutating}
						/>
					</div>
				</div>
			</TabsContent>

			{/* `@container` so the ticket's field grid sizes against the panel rather
			    than the viewport — a `sm:` breakpoint would fire off the window width
			    and cram four columns into a 440px sheet. */}
			<TabsContent
				value="diagnosis"
				className="@container mt-0 min-h-0 flex-1 overflow-y-auto"
			>
				{incidentPending && <IncidentDetailSkeleton />}
				{!incidentPending && (incidentError || !incident) && (
					<IncidentDetailError onRetry={() => void refetchIncident()} />
				)}
				{!incidentPending && !incidentError && incident && (
					<IncidentDetail incident={incident} />
				)}
			</TabsContent>

			<TabsContent value="activity" className="mt-0 min-h-0 flex-1 overflow-y-auto">
				<div className="p-4">
					<ActivityFeed
						incidentId={assignment.incident_id}
						events={events}
						isPending={eventsPending}
						canComment={actingOperatorId !== null}
					/>
				</div>
			</TabsContent>
		</Tabs>
	);
}
