import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '@shared/lib/api';
import type {
	SignalReading,
	SignalStreamEvent,
} from '@shared/types';

const RECONNECT_DELAY_MS = 3000;
/** Matches BUFFER_MAXLEN in app/streaming/manager.py (~5 min at 1 Hz). */
const MAX_POINTS = 300;

export type SignalConnectionStatus = 'connecting' | 'live' | 'error';

/**
 * Subscribes to `GET /stream/signals?bus_id=<bus>`.
 *
 * The server sends one `snapshot` frame (the bus's rolling buffer) and then a
 * `reading` frame per sample; its 15s heartbeat is an SSE comment, so it never
 * fires a message event. Readings are held in component state, bounded to the
 * same length as the server buffer so memory can't grow without limit.
 */
export function useSignalStream(busId: string | null) {
	const [readings, setReadings] = useState<SignalReading[]>([]);
	const [status, setStatus] = useState<SignalConnectionStatus>('connecting');
	// Kept in a ref so the reconnect timer can be cleared without re-subscribing.
	const retryRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

	useEffect(() => {
		if (!busId) {
			setReadings([]);
			setStatus('connecting');
			return;
		}

		let source: EventSource | null = null;
		let closed = false;

		setReadings([]);
		setStatus('connecting');

		const connect = () => {
			const url = `${API_BASE_URL}/stream/signals?bus_id=${encodeURIComponent(busId)}`;
			// No credentials — the API runs CORS with allow_credentials=False.
			source = new EventSource(url);

			source.onopen = () => setStatus('live');

			source.onmessage = (event) => {
				let payload: SignalStreamEvent;
				try {
					payload = JSON.parse(event.data) as SignalStreamEvent;
				} catch {
					return;
				}

				setStatus('live');

				if (payload.type === 'snapshot') {
					setReadings(payload.readings.slice(-MAX_POINTS));
					return;
				}

				if (payload.type === 'reading') {
					const { type: _type, ...reading } = payload;
					setReadings((current) => {
						const next = [...current, reading as SignalReading];
						return next.length > MAX_POINTS
							? next.slice(next.length - MAX_POINTS)
							: next;
					});
				}
			};

			source.onerror = () => {
				source?.close();
				if (closed) return;
				setStatus('error');
				retryRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
			};
		};

		connect();

		return () => {
			closed = true;
			clearTimeout(retryRef.current);
			source?.close();
		};
	}, [busId]);

	return { readings, status };
}
