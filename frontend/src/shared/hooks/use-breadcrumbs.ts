import { useLocation } from 'react-router';
import { type BreadcrumbItem as BreadcrumbItemType } from '../types';

const routeLabels: Record<string, string> = {
	'': 'Overview',
	incidents: 'Incidents',
};

export default function useBreadcrumbs(): BreadcrumbItemType[] {
	const { pathname } = useLocation();
	const segments = pathname.split('/').filter(Boolean);

	if (segments.length === 0) {
		return [{ title: 'Overview', href: '/' }];
	}

	const crumbs: BreadcrumbItemType[] = [{ title: 'Overview', href: '/' }];
	let path = '';

	for (const segment of segments) {
		path += `/${segment}`;
		const label = routeLabels[segment] ?? segment;
		crumbs.push({ title: label, href: path });
	}

	return crumbs;
}
