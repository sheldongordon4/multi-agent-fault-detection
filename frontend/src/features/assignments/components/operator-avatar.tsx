import { cn } from '@shared/lib/utils';
import { avatarClass, initialsOf } from '../utils/helpers';

/**
 * Initials chip for an operator. Colour is hashed from the id so one person
 * looks the same everywhere; the name is always available as a tooltip, because
 * two-letter initials collide and colour alone is never the signal.
 */
export function OperatorAvatar({
	operatorId,
	name,
	initials,
	size = 'sm',
	className,
}: {
	operatorId: string | null | undefined;
	name: string | null | undefined;
	initials?: string | null;
	size?: 'sm' | 'md';
	className?: string;
}) {
	const label = initials?.trim() || initialsOf(name);

	return (
		<span
			className={cn(
				'inline-flex shrink-0 items-center justify-center rounded-full font-mono font-medium text-white',
				size === 'sm' ? 'size-5 text-[9px]' : 'size-7 text-[11px]',
				avatarClass(operatorId),
				className
			)}
			title={name ?? undefined}
			aria-hidden={!!name}
		>
			{label}
		</span>
	);
}

/** The empty seat — an unassigned ticket. */
export function UnassignedAvatar({ className }: { className?: string }) {
	return (
		<span
			className={cn(
				'border-border text-muted-foreground inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-dashed text-[11px] leading-none',
				className
			)}
			aria-hidden
		>
			+
		</span>
	);
}
