import { type PropsWithChildren } from 'react';
import { AppContent } from '@shared/components/app/app-content';
import { AppShell } from '@shared/components/app/app-shell';
import { AppSidebar } from '@shared/components/app/app-sidebar';
import { AppSidebarHeader } from '@shared/components/app/app-sidebar-header';
import { useIncidentStream } from '@features/incidents/hooks/use-incident-stream';

interface AppSidebarLayoutProps extends PropsWithChildren {
	/**
	 * 'full-bleed' hands the page a fixed-height, non-scrolling box so it can
	 * paint edge to edge (the Incidents map background). The default scrolls,
	 * which would break anything positioned absolutely against the viewport.
	 */
	variant?: 'scroll' | 'full-bleed';
}

export default function AppSidebarLayout({
	children,
	variant = 'scroll',
}: AppSidebarLayoutProps) {
	// One SSE connection for the whole console: refreshes incident data and
	// raises a toast whenever the coordinator publishes a new fault ticket.
	useIncidentStream();

	return (
		<AppShell variant="sidebar">
			<AppSidebar />
			<AppContent variant="sidebar" className="min-h-0 overflow-hidden">
				<AppSidebarHeader />
				<div
					className={
						variant === 'full-bleed'
							? 'relative min-h-0 flex-1 overflow-hidden'
							: 'flex-1 overflow-y-auto'
					}
				>
					{children}
				</div>
			</AppContent>
		</AppShell>
	);
}
