import api from '@shared/lib/api';
import type { BusListResponse } from '@shared/types';

/**
 * GET /stream/buses — buses with a live rolling buffer.
 * Empty until a producer publishes to `raw.signals`.
 */
export async function fetchSignalBuses(): Promise<BusListResponse> {
	const response = await api.get<BusListResponse>('/stream/buses');
	return response.data;
}
