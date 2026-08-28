import { lazy } from 'react';
import {
	createBrowserRouter,
	RouterProvider,
	type RouteObject,
} from 'react-router';
import AppLayout from '../layouts/app-layout';
import LoadingPage from '../pages/loading';

const NotFound = lazy(() => import('../pages/not-found'));
const Incidents = lazy(() => import('../../features/incidents/pages/incidents'));

// MAFD is an operator dashboard with no auth: a single app shell wraps all routes.
const routes: RouteObject[] = [
	{
		path: '/',
		Component: AppLayout,
		HydrateFallback: () => <LoadingPage message="Loading MAFD…" />,
		children: [
			// Incidents IS the console now: the map, the list and the overview
			// drawer all live on it, so there's nothing left for a separate
			// landing page to show.
			{ index: true, Component: Incidents },
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
