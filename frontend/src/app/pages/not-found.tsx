import { ArrowLeft, Home, LayoutDashboard, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router';
import AppLogoIcon from '../../shared/components/app/app-logo-icon';
import { Button } from '../../shared/components/ui/button';

export default function NotFound() {
	const handleGoBack = () => {
		if (window.history.length > 1) {
			window.history.back();
			return;
		}
		window.location.href = '/';
	};

	return (
		<div className="bg-background flex min-h-full items-center justify-center px-6 py-16">
			<div className="w-full max-w-md text-center">
				<div className="bg-muted text-primary mx-auto mb-6 flex size-14 items-center justify-center rounded-xl">
					<TriangleAlert className="size-7" />
				</div>

				<p className="text-muted-foreground font-mono text-xs tracking-[0.28em] uppercase">
					Error · 404
				</p>
				<h1 className="mt-3 text-3xl font-semibold tracking-tight">
					Route not found
				</h1>
				<p className="text-muted-foreground mt-3 text-sm leading-6">
					This path doesn't map to any view in the MAFD console. It may have
					moved, or the URL has a typo.
				</p>

				<div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
					<Button asChild className="gap-2">
						<Link to="/">
							<LayoutDashboard className="size-4" />
							Go to Overview
						</Link>
					</Button>
					<Button variant="outline" className="gap-2" onClick={handleGoBack}>
						<ArrowLeft className="size-4" />
						Go back
					</Button>
				</div>

				<div className="text-muted-foreground/70 mt-10 flex items-center justify-center gap-2 text-xs">
					<AppLogoIcon className="text-primary size-4" />
					<Link
						to="/"
						className="hover:text-foreground inline-flex items-center gap-1"
					>
						<Home className="size-3" /> MAFD Console
					</Link>
				</div>
			</div>
		</div>
	);
}
