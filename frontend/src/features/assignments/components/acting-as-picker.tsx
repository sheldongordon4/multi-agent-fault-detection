import { useStore } from '@app/store';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from '@shared/components/ui/tooltip';
import { ROLE_LABELS } from '../utils/helpers';
import { useFetchOperators } from '../hooks/use-fetch-operators';
import { OperatorAvatar } from './operator-avatar';

/**
 * Who this terminal is acting as.
 *
 * MAFD has no auth, so this is a claim rather than a sign-in: it persists per
 * browser and rides along as `X-Actor-Id` so the activity log can say who
 * changed what. Anyone at the terminal can pick any name — the log is
 * attributed, not authenticated (see app/assignments/models.py::Operator).
 *
 * It lives in this page's header rather than the sidebar because the sidebar is
 * pinned to its icon rail (`open={false}` in app-shell.tsx), which would hide it
 * permanently — and an unset actor silently downgrades every entry in the log to
 * "system".
 */
export function ActingAsPicker() {
	const actingOperatorId = useStore((state) => state.actingOperatorId);
	const setActingOperatorId = useStore((state) => state.setActingOperatorId);
	const { operators } = useFetchOperators();

	const selected =
		operators.find((operator) => operator.id === actingOperatorId) ?? null;

	// Nothing to choose from until the roster is seeded; an empty select would
	// just look broken. scripts/seed_operators.py fills it.
	if (operators.length === 0) return null;

	return (
		<div className="flex items-center gap-2">
			<span className="text-muted-foreground hidden font-mono text-[10px] tracking-wider uppercase sm:inline">
				Acting as
			</span>

			<Select
				value={actingOperatorId ?? ''}
				onValueChange={setActingOperatorId}
			>
				<Tooltip>
					<TooltipTrigger asChild>
						<SelectTrigger
							className="h-8 w-[190px] text-xs"
							aria-label="Choose which operator this terminal is acting as"
						>
							{/*
							  The placeholder is load-bearing, not decoration: Radix renders it
							  INSTEAD of these children whenever no value is set, so dropping it
							  leaves the trigger an empty box — and this is the control that
							  decides whether the activity log says a name or "system".
							*/}
							<SelectValue placeholder="Choose operator">
								{/* Only ever rendered with a value set, hence no unset branch. */}
								<span className="flex min-w-0 items-center gap-2">
									{selected && (
										<OperatorAvatar
											operatorId={selected.id}
											name={selected.name}
											initials={selected.initials}
										/>
									)}
									<span className="truncate">{selected?.name}</span>
								</span>
							</SelectValue>
						</SelectTrigger>
					</TooltipTrigger>
					<TooltipContent side="bottom" className="max-w-[260px]">
						{selected
							? 'Changes you make are logged against this name. MAFD has no sign-in, so this is a claim, not a credential.'
							: 'Pick a name so your changes are logged against it. Until then they are recorded as "system".'}
					</TooltipContent>
				</Tooltip>

				<SelectContent align="end">
					{operators.map((operator) => (
						<SelectItem key={operator.id} value={operator.id}>
							<span className="flex min-w-0 items-center gap-2">
								<OperatorAvatar
									operatorId={operator.id}
									name={operator.name}
									initials={operator.initials}
								/>
								<span className="truncate">{operator.name}</span>
								<span className="text-muted-foreground ml-auto pl-3 font-mono text-[10px] whitespace-nowrap">
									{ROLE_LABELS[operator.role]}
								</span>
							</span>
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		</div>
	);
}
