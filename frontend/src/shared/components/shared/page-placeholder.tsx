import { type LucideIcon } from 'lucide-react';
import { Badge } from '../ui/badge';

interface PagePlaceholderProps {
	icon: LucideIcon;
	title: string;
	description: string;
	/** Which build phase will flesh this view out (e.g. "Phase 1"). */
	phase?: string;
}

/**
 * Phase-0 scaffold placeholder. Each MAFD view renders one of these until its
 * feature slice is implemented, so the shell + navigation are fully walkable.
 */
export function PagePlaceholder({
	icon: Icon,
	title,
	description,
	phase,
}: PagePlaceholderProps) {
	return (
		<div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-6 py-16 text-center">
			<div className="bg-muted text-primary mb-6 flex size-16 items-center justify-center rounded-2xl">
				<Icon className="size-8" />
			</div>
			<div className="mb-2 flex items-center gap-2">
				<h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
				{phase && (
					<Badge variant="outline" className="font-mono text-[11px]">
						{phase}
					</Badge>
				)}
			</div>
			<p className="text-muted-foreground max-w-md text-sm leading-6">
				{description}
			</p>
		</div>
	);
}
