import { Breadcrumbs } from '../navigation/breadcrumbs';
import { ModeToggle } from '../shared/mode-toggle';
import useBreadcrumbs from '../../hooks/use-breadcrumbs';

export function AppSidebarHeader() {
	const breadcrumbs = useBreadcrumbs();

	return (
		<header className="bg-sidebar border-sidebar-border/50 flex h-16 shrink-0 items-center justify-between gap-2 border-b px-6 transition-[width,height] duration-300 ease-in-out group-has-data-[collapsible=icon]/sidebar-wrapper:h-12 md:px-4">
		
			<div className="flex items-center gap-3">
				<Breadcrumbs breadcrumbs={breadcrumbs} />
				<ModeToggle />
			</div>
		</header>
	);
}
