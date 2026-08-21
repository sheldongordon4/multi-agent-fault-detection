import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { API_BASE_URL } from '@shared/lib/api';
import type { NotificationStreamEvent } from '@shared/types';
import { incidentQueryKeys } from '../utils/query-keys';

const RECONNECT_DELAY_MS = 3000;

/**
 * Subscribes to the broadcast SSE channel (`GET /notifications/stream`) and
 * refreshes the incident list when the coordinator publishes a new ticket.
 *
 * The backend emits `{"type": <NotificationType>, ...data}`; its 15s heartbeat
 * is an SSE comment, so it never fires a message event. Mounted once from the
 * app layout so a single connection serves the whole console.
 */
export function useIncidentStream() {
	const queryClient = useQueryClient();

	useEffect(() => {
		const url = `${API_BASE_URL}/notifications/stream`;
		let source: EventSource | null = null;
		let retryTimeout: ReturnType<typeof setTimeout> | undefined;
		let closed = false;

		const refreshIncidentList = () => {
			queryClient.invalidateQueries({
				queryKey: incidentQueryKeys.all,
				predicate: (query) => query.queryKey[1] === 'list',
			});
		};

		const connect = () => {
			// No `withCredentials` — the API runs CORS with allow_credentials=False
			// (see shared/lib/api.ts), so a credentialed stream would be blocked.
			source = new EventSource(url);

			source.onmessage = (event) => {
				let payload: NotificationStreamEvent;
				try {
					payload = JSON.parse(event.data) as NotificationStreamEvent;
				} catch {
					return;
				}

				if (payload.type === 'faultticket.ready') {
					refreshIncidentList();
					// Also refresh the detail if this incident is already cached.
					if (payload.incident_id) {
						queryClient.invalidateQueries({
							queryKey: incidentQueryKeys.detail(payload.incident_id),
						});
					}
					toast.warning(payload.title ?? 'New fault ticket', {
						description: payload.body ?? undefined,
					});
					return;
				}

				if (payload.type === 'incident.detected') {
					refreshIncidentList();
				}
			};

			source.onerror = () => {
				source?.close();
				if (closed) return;
				retryTimeout = setTimeout(connect, RECONNECT_DELAY_MS);
			};
		};

		connect();

		return () => {
			closed = true;
			clearTimeout(retryTimeout);
			source?.close();
		};
	}, [queryClient]);
}

export default useIncidentStream;
