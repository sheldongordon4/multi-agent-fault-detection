import type { LucideIcon } from 'lucide-react';


export type Theme = 'dark' | 'light' | 'system';
export type Language = 'en' | 'de' | 'es' | 'fr' | 'ja';

export type Severity = 'low' | 'medium' | 'high';

export type TicketStatus = 'diagnosed' | 'acknowledged' | 'resolved';

export type NotificationType = 'incident.detected' | 'faultticket.ready';

export const SEVERITIES: Severity[] = ['low', 'medium', 'high'];
export const TICKET_STATUSES: TicketStatus[] = [
	'diagnosed',
	'acknowledged',
	'resolved',
];


export interface EvidenceWindow {
	start_timestamp: string;
	end_timestamp: string;
	metric: string;
	description: string;
}

export interface KBCitation {
	source_id: string;
	title: string;
	section?: string | null;
	url?: string | null;
	snippet?: string | null;
}

export interface TopBus {
	bus: string;
	minVa?: number | null;
	maxIa?: number | null;
	maxI0I1?: number | null;
	maxI2I1?: number | null;
}


export interface FaultTicket {
	ticket_id: string;
	scenario: string;
	bus_id: string;
	fault_type: string;
	severity: Severity;
	status: TicketStatus;
	summary: string;
	root_cause: string;
	recommended_actions: string[];
	evidence: EvidenceWindow[];
	kb_citations: KBCitation[];
	created_at: string;
}


export type RawFaultTicket = Partial<FaultTicket> & Record<string, unknown>;


export interface TicketSummary {
	incident_id: string;
	ticket_id: string;
	scenario: string | null;
	bus_id: string | null;
	fault_type: string | null;
	severity: string | null;
	status: string | null;
	summary: string | null;
	created_at: string;
}

export interface TicketListResponse {
	items: TicketSummary[];
	count: number;
}

export interface TicketDetail extends TicketSummary {
	raw: RawFaultTicket;
}


export interface DiagnoseRequest {
	feeder: string;
	incident_id?: string | null;
	severity?: string | null;
	anomaly_score?: number | null;
	top_buses?: TopBus[];
}


/**
 * A frame off SSE `GET /notifications/stream` — the broadcast channel the
 * coordinator uses to announce new fault tickets. The payload is flattened as
 * `{"type": <NotificationType>, ...data}` (app/notification/sse.py); the 15s
 * heartbeat is an SSE comment, so it never fires a message event.
 */
export interface NotificationStreamEvent {
	type: NotificationType | string;
	id?: string;
	title?: string;
	body?: string;
	incident_id?: string | null;
	bus_id?: string | null;
	severity?: string | null;
	[key: string]: unknown;
}


/**
 * One SCADA reading off `raw.signals` (see scripts/produce_signals.py).
 * The streaming service keeps a bounded per-bus deque of these (~300 samples,
 * app/streaming/manager.py) and fans them out over SSE.
 */
export interface SignalReading {
	timestamp: string;
	bus_id: string;
	scenario?: string;
	voltage_kv: number;
	current_a: number;
	frequency_hz: number;
	temperature_c: number;
}

/** Which numeric channels a reading carries — drives the chart metric picker. */
export type SignalMetric =
	| 'voltage_kv'
	| 'current_a'
	| 'frequency_hz'
	| 'temperature_c';

/** Sent once on connect: the bus's current rolling buffer. */
export interface SignalSnapshotEvent {
	type: 'snapshot';
	bus_id: string;
	readings: SignalReading[];
}

/** Sent per live sample thereafter (reading fields are flattened in). */
export type SignalReadingEvent = { type: 'reading' } & SignalReading;

export type SignalStreamEvent = SignalSnapshotEvent | SignalReadingEvent;

/** app/streaming/schemas.py::BusListResponse — GET /stream/buses */
export interface BusListResponse {
	items: string[];
	count: number;
}


export interface ReadinessResponse {
	ready: boolean;
	checks: Record<string, boolean>;
}


export interface BreadcrumbItem {
	title: string;
	href: string;
}

export interface NavGroup {
	title: string;
	items: NavItem[];
}

export interface NavItem {
	title: string;
	href: string;
	icon?: LucideIcon | null;
	isActive?: boolean;
	params?: string;
}
