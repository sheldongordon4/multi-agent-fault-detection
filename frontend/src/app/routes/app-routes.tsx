import { lazy } from 'react';
import {
	createBrowserRouter,
	RouterProvider,
	type RouteObject,
} from 'react-router';
import AppLayout from '../layouts/app-layout';
import LoadingPage from '../pages/loading';

const NotFound = lazy(() => import('../pages/not-found'));
const Overview = lazy(() => import('../../features/overview/pages/overview'));
const Incidents = lazy(() => import('../../features/incidents/pages/incidents'));

// MAFD is an operator dashboard with no auth: a single app shell wraps all routes.
const routes: RouteObject[] = [
	{
		path: '/',
		Component: AppLayout,
		HydrateFallback: () => <LoadingPage message="Loading MAFD…" />,
		children: [
			{ index: true, Component: Overview },
			{ path: 'incidents', Component: Incidents },
			{ path: 'incidents/:incidentId', Component: Incidents },
			{ path: '*', Component: NotFound },
		],
	},
];

const router = createBrowserRouter(routes);

export default function AppRoutes() {
	return <RouterProvider router={router} />;
}
