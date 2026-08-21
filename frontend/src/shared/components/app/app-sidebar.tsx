import { Link } from 'react-router';
import { TriangleAlert } from 'lucide-react';

import { type NavItem } from '../../types';
import AppLogo from './app-logo';
import AppLogoIcon from './app-logo-icon';
import { NavMain } from '../navigation/nav-main';
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarHeader,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarSeparator,
} from '../ui/sidebar';

const mainNavItems: NavItem[] = [
	{ title: 'Incidents', href: '/', icon: TriangleAlert },
];

export function AppSidebar() {
	return (
		<Sidebar collapsible="icon" variant="sidebar">
			<SidebarHeader>
				<SidebarMenu>
					<SidebarMenuItem>
						<SidebarMenuButton size="lg" asChild>
							<Link to="/">
								<AppLogo />
							</Link>
						</SidebarMenuButton>
					</SidebarMenuItem>
				</SidebarMenu>
			</SidebarHeader>

			<SidebarSeparator />

			<SidebarContent>
				<NavMain items={mainNavItems} />
			</SidebarContent>

			<SidebarFooter>
				<SidebarMenu>
					<SidebarMenuItem>
						<div className="text-muted-foreground flex items-center gap-2 px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden">
							<AppLogoIcon className="text-primary size-4" />
							<span className="font-mono">MAFD · v0.1</span>
						</div>
					</SidebarMenuItem>
				</SidebarMenu>
			</SidebarFooter>
		</Sidebar>
	);
}
