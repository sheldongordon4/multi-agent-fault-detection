import { useState } from 'react';
import { Cpu, Send } from 'lucide-react';
import { Button } from '@shared/components/ui/button';
import { Skeleton } from '@shared/components/ui/skeleton';
import { Textarea } from '@shared/components/ui/textarea';
import { cn } from '@shared/lib/utils';
import type { AssignmentEvent } from '@shared/types';
import { formatTimestamp } from '@features/incidents/utils/helpers';
import { useAddComment } from '../hooks/use-add-comment';
import { PRIORITY_LABELS, workStateLabel } from '../utils/helpers';
import { OperatorAvatar } from './operator-avatar';

/**
 * One line of prose per event.
 *
 * The log stores raw values (`assigned` → an operator id, `state_changed` →
 * `in_progress`); rendering them verbatim would make the feed unreadable, so the
 * ids are resolved and the enums given their display labels here.
 */
export function describeEvent(event: AssignmentEvent): string {
	const actor = event.actor_name ?? 'The system';

	switch (event.kind) {
		case 'assigned':
			return `${actor} assigned this ticket`;
		case 'unassigned':
			return `${actor} returned this ticket to the queue`;
		case 'state_changed':
			return `${actor} moved this to ${workStateLabel(event.to_value ?? '')}`;
		case 'priority_changed':
			return `${actor} set priority to ${
				PRIORITY_LABELS[event.to_value as keyof typeof PRIORITY_LABELS] ??
				event.to_value
			}`;
		case 'due_changed':
			return `${actor} changed the due time`;
		case 'note_changed':
			return event.body
				? `${actor} updated the disposition note`
				: `${actor} cleared the disposition note`;
		case 'commented':
			return `${actor} commented`;
		default:
			return `${actor} updated this ticket`;
	}
}

function EventRow({ event, isLast }: { event: AssignmentEvent; isLast: boolean }) {
	const quoted = event.kind === 'commented' || event.kind === 'note_changed';

	return (
		<li className="flex gap-3">
			<div className="flex flex-col items-center">
				{event.actor_id ? (
					<OperatorAvatar operatorId={event.actor_id} name={event.actor_name} />
				) : (
					<span
						className="bg-muted text-muted-foreground border-border flex size-5 shrink-0 items-center justify-center rounded-full border"
						title="Recorded without an operator"
					>
						<Cpu className="size-2.5" />
					</span>
				)}
				{!isLast && <span className="bg-border mt-1 w-px flex-1" aria-hidden />}
			</div>

			<div className="min-w-0 pb-4">
				<p className="text-muted-foreground text-xs">
					<span className="text-foreground font-medium">{describeEvent(event)}</span>
				</p>
				<p className="text-muted-foreground/70 mt-0.5 font-mono text-[10px]">
					{formatTimestamp(event.created_at)}
				</p>
				{quoted && event.body && (
					<p className="border-border mt-1.5 border-l-2 pl-2.5 text-xs leading-relaxed">
						{event.body}
					</p>
				)}
			</div>
		</li>
	);
}

export function ActivityFeed({
	incidentId,
	events,
	isPending,
	canComment,
}: {
	incidentId: string;
	events: AssignmentEvent[];
	isPending: boolean;
	/** False until this terminal says who it is — an unattributed comment is noise. */
	canComment: boolean;
}) {
	const [draft, setDraft] = useState('');
	const { mutate, isPending: isPosting } = useAddComment(incidentId);

	const submit = () => {
		const body = draft.trim();
		if (!body) return;
		mutate(body, { onSuccess: () => setDraft('') });
	};

	return (
		<div className="flex min-h-0 flex-col gap-3">
			{isPending && (
				<div className="space-y-3">
					{Array.from({ length: 3 }).map((_, index) => (
						<Skeleton key={index} className="h-10 w-full" />
					))}
				</div>
			)}

			{!isPending && events.length === 0 && (
				<p className="text-muted-foreground py-4 text-center text-xs">
					Nothing has happened to this ticket yet.
				</p>
			)}

			{!isPending && events.length > 0 && (
				<ol className="min-h-0 overflow-y-auto">
					{events.map((event, index) => (
						<EventRow
							key={event.id}
							event={event}
							isLast={index === events.length - 1}
						/>
					))}
				</ol>
			)}

			<div className="border-border/60 border-t pt-3">
				<Textarea
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					onKeyDown={(e) => {
						// Enter alone inserts a newline — field notes run to several
						// lines. Cmd/Ctrl+Enter is the send shortcut.
						if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
							e.preventDefault();
							submit();
						}
					}}
					placeholder={
						canComment
							? 'Add a note for the next shift…'
							: 'Choose who you are acting as to comment'
					}
					disabled={!canComment || isPosting}
					className={cn('min-h-[64px] resize-none text-xs')}
					aria-label="Add a comment"
				/>
				<div className="mt-2 flex items-center justify-between gap-2">
					<span className="text-muted-foreground/70 font-mono text-[10px]">
						⌘/Ctrl + ⏎
					</span>
					<Button
						size="sm"
						onClick={submit}
						disabled={!canComment || isPosting || !draft.trim()}
						className="h-7 gap-1.5 text-xs"
					>
						<Send className="size-3" />
						Comment
					</Button>
				</div>
			</div>
		</div>
	);
}
