import AppLogoIcon from './app-logo-icon';

export default function AppLogo() {
	return (
		<div className="flex items-center gap-2">
			<div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-md">
				<AppLogoIcon className="size-5" />
			</div>
			<div className="grid flex-1 text-left leading-tight">
				<span className="truncate text-sm font-semibold tracking-tight">
					MAFD
				</span>
				<span className="text-muted-foreground truncate text-[11px]">
					Fault Detection
				</span>
			</div>
		</div>
	);
}
