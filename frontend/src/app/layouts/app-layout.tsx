import { Outlet, useLocation } from 'react-router';
import AppLayoutTemplate from './app/app-sidebar-layout';

// Incidents paints a full-bleed map behind floating panels, so it needs a
// non-scrolling, fixed-height content box. Everything else scrolls normally.
//
// This is decided here rather than by giving Incidents its own layout route: the
// shell owns the incident SSE stream, so remounting it on navigation would drop
// and re-open that connection (and rebuild the map) every time.
// Prefixes matched with a trailing slash. '/' is deliberately absent: it now
// redirects to /overview, which scrolls. Nothing may be matched with a bare
// startsWith on '/' either — it prefixes every route, which would make even the
// 404 page full-bleed and unscrollable.
const FULL_BLEED_EXACT: string[] = [];
const FULL_BLEED_PREFIXES = ['/incidents'];

const AppLayout = () => {
	const { pathname } = useLocation();
	const fullBleed =
		FULL_BLEED_EXACT.includes(pathname) ||
		FULL_BLEED_PREFIXES.some(
			(prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
		);

	return (
		<AppLayoutTemplate variant={fullBleed ? 'full-bleed' : 'scroll'}>
			<Outlet />
		</AppLayoutTemplate>
	);
};

export default AppLayout;
