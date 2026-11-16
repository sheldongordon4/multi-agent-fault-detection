import {
	Select,
	SelectContent,
	SelectItem,
	SelectSeparator,
	SelectTrigger,
	SelectValue,
} from '@shared/components/ui/select';
import { cn } from '@shared/lib/utils';
import type { Operator } from '@shared/types';
import { ROLE_LABELS } from '../utils/helpers';
import { OperatorAvatar, UnassignedAvatar } from './operator-avatar';

/** Sentinel for "no assignee" — Radix Select can't hold an empty string value. */
export const UNASSIGNED_VALUE = '__unassigned__';

export function AssigneePicker({
	value,
	operators,
	onChange,
	disabled,
	className,
	fallbackName,
	fallbackInitials,
	'aria-label': ariaLabel = 'Assignee',
}: {
	value: string | null;
	operators: Operator[];
	onChange: (operatorId: string | null) => void;
	disabled?: boolean;
	className?: string;
	/**
	 * The assignee as the ticket itself reports them. The roster omits
	 * deactivated operators, so without this a ticket held by someone who has
	 * left the shift would render as "Unassigned" and be picked up twice.
	 */
	fallbackName?: string | null;
	fallbackInitials?: string | null;
	'aria-label'?: string;
}) {
	const selected = operators.find((operator) => operator.id === value) ?? null;
	const offRoster = value !== null && selected === null;

	// On-shift first: the question being answered is "who can take this now".
	const onShift = operators.filter((operator) => operator.on_shift);
	const offShift = operators.filter((operator) => !operator.on_shift);

	return (
		<Select
			value={value ?? UNASSIGNED_VALUE}
			onValueChange={(next) =>
				onChange(next === UNASSIGNED_VALUE ? null : next)
			}
			disabled={disabled}
		>
			<SelectTrigger
				className={cn('h-8 w-full min-w-0 text-xs', className)}
				aria-label={ariaLabel}
			>
				<SelectValue>
					<span className="flex min-w-0 items-center gap-2">
						{selected || offRoster ? (
							<OperatorAvatar
								operatorId={value}
								name={selected?.name ?? fallbackName}
								initials={selected?.initials ?? fallbackInitials}
							/>
						) : (
							<UnassignedAvatar />
						)}
						<span className="truncate">
							{selected?.name ?? (offRoster ? (fallbackName ?? 'Off roster') : 'Unassigned')}
						</span>
					</span>
				</SelectValue>
			</SelectTrigger>

			<SelectContent>
				<SelectItem value={UNASSIGNED_VALUE}>
					<span className="flex items-center gap-2">
						<UnassignedAvatar />
						Unassigned
					</span>
				</SelectItem>

				{onShift.length > 0 && <SelectSeparator />}
				{onShift.map((operator) => (
					<OperatorOption key={operator.id} operator={operator} />
				))}

				{offShift.length > 0 && <SelectSeparator />}
				{offShift.map((operator) => (
					<OperatorOption key={operator.id} operator={operator} offShift />
				))}
			</SelectContent>
		</Select>
	);
}

function OperatorOption({
	operator,
	offShift = false,
}: {
	operator: Operator;
	offShift?: boolean;
}) {
	return (
		<SelectItem value={operator.id}>
			<span className="flex min-w-0 items-center gap-2">
				<OperatorAvatar
					operatorId={operator.id}
					name={operator.name}
					initials={operator.initials}
				/>
				<span className="truncate">{operator.name}</span>
				<span className="text-muted-foreground ml-auto pl-3 font-mono text-[10px] whitespace-nowrap">
					{offShift ? 'off shift' : `${operator.open_count}/${operator.capacity}`}
					{' · '}
					{ROLE_LABELS[operator.role]}
				</span>
			</span>
		</SelectItem>
	);
}
