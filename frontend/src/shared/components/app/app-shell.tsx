import { SidebarProvider } from '../ui/sidebar';

interface AppShellProps {
	children: React.ReactNode;
	variant?: 'header' | 'sidebar';
}

export function AppShell({ children, variant = 'header' }: AppShellProps) {
	if (variant === 'header') {
		return <div className="flex min-h-svh w-full flex-col">{children}</div>;
	}

	return (
		// `open` (controlled) rather than `defaultOpen`: the sidebar stays collapsed
		// to its icon rail permanently. This also neutralises the persisted
		// `sidebar_state` cookie and the Ctrl/Cmd+B shortcut, so there's no way to
		// end up expanded — matching the removed toggle in AppSidebarHeader.
		<SidebarProvider open={false} className="fixed inset-0 overflow-hidden">
			{children}
		</SidebarProvider>
	);
}
