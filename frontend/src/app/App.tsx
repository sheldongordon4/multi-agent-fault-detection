import { ErrorBoundary } from 'react-error-boundary';
import './App.css';
import ErrorFallback from './pages/error';
import AppRoutes from './routes/app-routes';
import { Suspense } from 'react';
import LoadingPage from './pages/loading';
import QueryProvider from './providers/query-provider';
import { Toaster } from '../shared/components/ui/sonner';

export default function App() {
	return (
		<ErrorBoundary FallbackComponent={ErrorFallback}>
			<Suspense fallback={<LoadingPage />}>
				<QueryProvider>
					<AppRoutes />
					<Toaster position="bottom-right" richColors closeButton />
				</QueryProvider>
			</Suspense>
		</ErrorBoundary>
	);
}
