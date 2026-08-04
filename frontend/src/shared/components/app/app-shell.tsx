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
		<SidebarProvider
			defaultOpen={true}
			className="fixed inset-0 overflow-hidden"
		>
			{children}
		</SidebarProvider>
	);
}
