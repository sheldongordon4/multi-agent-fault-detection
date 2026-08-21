import type { Severity, TicketSummary } from '@shared/types';
import {
	normalizeSeverity,
	normalizeStatus,
	SEVERITY_RANK,
} from '@features/incidents/utils/helpers';
import { BUS_LOCATIONS, type BusLocation } from './bus-locations';

/** A mapped bus plus whatever the incident feed currently says about it. */
export interface BusStatus extends BusLocation {
	/** Worst active severity, or null when the bus has no active incidents. */
	severity: Severity | null;
	/** Number of active (unresolved) incidents on this bus. */
	activeCount: number;
	/** ISO timestamp of the newest active incident — drives recency fading. */
	latestAt: string | null;
	/** Id of the newest active incident, so arrivals can be detected. */
	latestIncidentId: string | null;
}

/** Anything older than this is drawn at minimum emphasis. */
const STALE_AFTER_MS = 30 * 60 * 1000;

/**
 * 1 = brand new, 0.35 = stale. Every marker looking equally urgent regardless of
 * age is misleading on an operator display: it hides where to look *now*.
 */
export function recencyWeight(latestAt: string | null, now = Date.now()): number {
	if (!latestAt) return 1;
	const then = new Date(latestAt).getTime();
	if (Number.isNaN(then)) return 1;
	const age = Math.max(0, now - then);
	if (age >= STALE_AFTER_MS) return 0.35;
	return 1 - 0.65 * (age / STALE_AFTER_MS);
}

/** Compact "how long ago" for tooltips. */
export function formatAge(latestAt: string | null, now = Date.now()): string {
	if (!latestAt) return '';
	const then = new Date(latestAt).getTime();
	if (Number.isNaN(then)) return '';
	const secs = Math.max(0, Math.round((now - then) / 1000));
	if (secs < 60) return `${secs}s ago`;
	const mins = Math.round(secs / 60);
	if (mins < 60) return `${mins}m ago`;
	const hours = Math.round(mins / 60);
	if (hours < 24) return `${hours}h ago`;
	return `${Math.round(hours / 24)}d ago`;
}

/**
 * Resolved tickets are history, not current grid state — a substation with three
 * resolved faults is healthy right now, and colouring it red would cry wolf.
 */
function isActive(incident: TicketSummary): boolean {
	return normalizeStatus(incident.status) !== 'resolved';
}

/**
 * Fold the incident feed onto the mapped buses.
 *
 * Buses with no incidents are still returned (severity: null) — an operator needs
 * to see that a site is healthy, not just that it's absent.
 */
export function deriveBusStatuses(incidents: TicketSummary[]): BusStatus[] {
	type Agg = {
		severity: Severity;
		count: number;
		latestAt: string | null;
		latestIncidentId: string | null;
	};
	const worst = new Map<string, Agg>();

	for (const incident of incidents) {
		if (!incident.bus_id || !isActive(incident)) continue;

		const severity = normalizeSeverity(incident.severity);
		const current = worst.get(incident.bus_id);

		if (!current) {
			worst.set(incident.bus_id, {
				severity,
				count: 1,
				latestAt: incident.created_at ?? null,
				latestIncidentId: incident.incident_id,
			});
			continue;
		}

		const isNewer =
			!!incident.created_at &&
			(!current.latestAt ||
				new Date(incident.created_at) > new Date(current.latestAt));

		worst.set(incident.bus_id, {
			severity:
				SEVERITY_RANK[severity] > SEVERITY_RANK[current.severity]
					? severity
					: current.severity,
			count: current.count + 1,
			latestAt: isNewer ? incident.created_at : current.latestAt,
			latestIncidentId: isNewer
				? incident.incident_id
				: current.latestIncidentId,
		});
	}

	return BUS_LOCATIONS.map((location) => {
		const hit = worst.get(location.busId);
		return {
			...location,
			severity: hit?.severity ?? null,
			activeCount: hit?.count ?? 0,
			latestAt: hit?.latestAt ?? null,
			latestIncidentId: hit?.latestIncidentId ?? null,
		};
	});
}

/**
 * Worst active severity per parish, keyed by parish name (matching the `parish`
 * property in jamaica-parishes.geojson) so MapLibre can tint the polygons.
 */
export function deriveParishSeverity(
	statuses: BusStatus[]
): Record<string, Severity> {
	const byParish: Record<string, Severity> = {};

	for (const status of statuses) {
		if (!status.severity) continue;
		const current = byParish[status.parish];
		if (
			!current ||
			SEVERITY_RANK[status.severity] > SEVERITY_RANK[current]
		) {
			byParish[status.parish] = status.severity;
		}
	}

	return byParish;
}

/** Shared severity palette. Only these should be saturated on the map. */
export const SEVERITY_COLOR: Record<Severity, string> = {
	high: '#ef4444', // red-500
	medium: '#f59e0b', // amber-500
	low: '#3b82f6', // blue-500
};

/** Healthy = mapped, reporting, no active incidents. */
export const HEALTHY_COLOR = '#22c55e'; // green-500

export function statusColor(severity: Severity | null): string {
	return severity ? SEVERITY_COLOR[severity] : HEALTHY_COLOR;
}
