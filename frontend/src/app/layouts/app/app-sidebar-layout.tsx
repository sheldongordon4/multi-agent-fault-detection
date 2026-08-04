import { type PropsWithChildren } from 'react';
import { AppContent } from '../../../shared/components/app/app-content';
import { AppShell } from '../../../shared/components/app/app-shell';
import { AppSidebar } from '../../../shared/components/app/app-sidebar';
import { AppSidebarHeader } from '../../../shared/components/app/app-sidebar-header';
import { useIncidentStream } from '../../../features/incidents/hooks/use-incident-stream';

export default function AppSidebarLayout({ children }: PropsWithChildren) {
	// One SSE connection for the whole console: refreshes incident data and
	// raises a toast whenever the coordinator publishes a new fault ticket.
	useIncidentStream();

	return (
		<AppShell variant="sidebar">
			<AppSidebar />
			<AppContent variant="sidebar" className="min-h-0 overflow-hidden">
				<AppSidebarHeader />
				<div className="flex-1 overflow-y-auto">{children}</div>
			</AppContent>
		</AppShell>
	);
}
