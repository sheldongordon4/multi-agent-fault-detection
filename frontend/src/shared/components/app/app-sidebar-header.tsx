import { Breadcrumbs } from '../navigation/breadcrumbs';
import { ModeToggle } from '../shared/mode-toggle';
import { PanelLeft } from 'lucide-react';
import { Separator } from '../ui/separator';
import { SidebarTrigger } from '../ui/sidebar';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import useBreadcrumbs from '../../hooks/use-breadcrumbs';

export function AppSidebarHeader() {
	const breadcrumbs = useBreadcrumbs();

	return (
		<header className="bg-sidebar border-sidebar-border/50 flex h-16 shrink-0 items-center justify-between gap-2 border-b px-6 transition-[width,height] duration-300 ease-in-out group-has-data-[collapsible=icon]/sidebar-wrapper:h-12 md:px-4">
			<div className="flex items-center gap-3">
				<Tooltip>
					<TooltipTrigger asChild>
						<SidebarTrigger icon={PanelLeft} />
					</TooltipTrigger>
					<TooltipContent side="right">Toggle sidebar</TooltipContent>
				</Tooltip>
				<Separator orientation="vertical" className="h-5" />
				<Breadcrumbs breadcrumbs={breadcrumbs} />
				<ModeToggle />
			</div>
		</header>
	);
}
