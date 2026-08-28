import { useLocation } from 'react-router';
import { type BreadcrumbItem as BreadcrumbItemType } from '../types';

const routeLabels: Record<string, string> = {
	incidents: 'Incidents',
};

/**
 * Breadcrumbs for the console.
 *
 * The root used to be a separate Overview page, so it was always the first crumb.
 * Overview is now a drawer on Incidents and `/` renders Incidents itself, so the
 * root crumb is "Incidents" — leaving it as "Overview" would name a page that no
 * longer exists.
 */
export default function useBreadcrumbs(): BreadcrumbItemType[] {
	const { pathname } = useLocation();
	const segments = pathname.split('/').filter(Boolean);

	const crumbs: BreadcrumbItemType[] = [{ title: 'Incidents', href: '/' }];

	// `/` and `/incidents` are the same screen — don't repeat the crumb.
	if (segments.length === 0 || (segments.length === 1 && segments[0] === 'incidents')) {
		return crumbs;
	}

	let path = '';
	for (const segment of segments) {
		path += `/${segment}`;
		if (segment === 'incidents') continue; // already the root crumb
		crumbs.push({ title: routeLabels[segment] ?? segment, href: path });
	}

	return crumbs;
}
