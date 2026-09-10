import { lazy } from 'react';
import {
	createBrowserRouter,
	Navigate,
	RouterProvider,
	type RouteObject,
} from 'react-router';
import AppLayout from '../layouts/app-layout';
import LoadingPage from '../pages/loading';

const NotFound = lazy(() => import('../pages/not-found'));
const Incidents = lazy(() => import('../../features/incidents/pages/incidents'));
const Overview = lazy(() => import('../../features/overview/pages/overview'));
const Assignments = lazy(
	() => import('../../features/assignments/pages/assignments')
);

// MAFD is an operator dashboard with no auth: a single app shell wraps all routes.
const routes: RouteObject[] = [
	{
		path: '/',
		Component: AppLayout,
		HydrateFallback: () => <LoadingPage message="Loading MAFD…" />,
		children: [
			// Overview is the landing page: it answers "how is the grid right now"
			// in one screen, which is the question an operator arrives with.
			//
			// A redirect rather than mounting Overview at both '/' and '/overview':
			// one canonical URL per page keeps the sidebar's active state honest
			// (nav-main matches on prefix) and makes a shared link unambiguous.
			{ index: true, element: <Navigate to="/overview" replace /> },
			{ path: 'overview', Component: Overview },
			{ path: 'incidents', Component: Incidents },
			{ path: 'incidents/:incidentId', Component: Incidents },
			// Ticket ownership gets its own page: the map screen is already three
			// layers deep, and this one is a table you scan, not a map you read.
			{ path: 'assignments', Component: Assignments },
			{ path: 'assignments/:incidentId', Component: Assignments },
			{ path: '*', Component: NotFound },
		],
	},
];

const router = createBrowserRouter(routes);

export default function AppRoutes() {
	return <RouterProvider router={router} />;
}
