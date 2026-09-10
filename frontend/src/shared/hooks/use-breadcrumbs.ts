import { useLocation } from 'react-router';
import { type BreadcrumbItem as BreadcrumbItemType } from '../types';

const routeLabels: Record<string, string> = {
	overview: 'Overview',
	incidents: 'Incidents',
	assignments: 'Assignments',
};

/**
 * Breadcrumbs for the console.
 *
 * Derived purely from the path, with no hardcoded root crumb. An earlier version
 * always prepended a fixed first crumb, which meant every page claimed to sit
 * under whichever page happened to be the landing page at the time — so
 * /overview rendered as "Incidents › overview" once the default moved.
 *
 * The console's pages are siblings, not a hierarchy: Overview, Incidents and
 * Assignments are three ways into the same data. So the trail is just the
 * segments, and a ticket id becomes a second crumb under its section.
 */
export default function useBreadcrumbs(): BreadcrumbItemType[] {
	const { pathname } = useLocation();
	const segments = pathname.split('/').filter(Boolean);

	// '/' redirects to /overview, so it is only ever seen in passing.
	if (segments.length === 0) {
		return [{ title: routeLabels.overview, href: '/overview' }];
	}

	const crumbs: BreadcrumbItemType[] = [];
	let path = '';

	for (const segment of segments) {
		path += `/${segment}`;
		crumbs.push({
			// Unknown segments are ids (an incident_id under /incidents or
			// /assignments), which have no label to look up and are shown as-is.
			title: routeLabels[segment] ?? segment,
			href: path,
		});
	}

	return crumbs;
}
