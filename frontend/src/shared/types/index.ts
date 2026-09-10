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


/* â”€â”€ Assignments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

/**
 * Operator-owned workflow state (app/assignments/constants.py::WorkState).
 *
 * Deliberately NOT `TicketStatus`. That one is the coordinator's diagnostic
 * status and is owned by the pipeline; this one is driven by operators. A ticket
 * can be `diagnosed` and `in_progress` at the same time.
 */
export type WorkState =
	| 'unassigned'
	| 'assigned'
	| 'in_progress'
	| 'blocked'
	| 'resolved'
	| 'closed';

export type Priority = 'p1' | 'p2' | 'p3' | 'p4';

export type OperatorRole =
	| 'control_room'
	| 'field_crew'
	| 'protection_eng'
	| 'supervisor';

export type AssignmentEventKind =
	| 'assigned'
	| 'unassigned'
	| 'state_changed'
	| 'priority_changed'
	| 'due_changed'
	| 'note_changed'
	| 'commented';

/** Board column order â€” also the order states are offered in the pickers. */
export const WORK_STATES: WorkState[] = [
	'unassigned',
	'assigned',
	'in_progress',
	'blocked',
	'resolved',
	'closed',
];

export const PRIORITIES: Priority[] = ['p1', 'p2', 'p3', 'p4'];

/** A roster entry. Not a user account â€” MAFD has no auth. */
export interface Operator {
	id: string;
	name: string;
	initials: string;
	role: OperatorRole;
	parish: string | null;
	capacity: number;
	on_shift: boolean;
	active: boolean;
	created_at: string;
	open_count: number;
}

export interface OperatorListResponse {
	items: Operator[];
	count: number;
}

/**
 * A fault ticket joined to its assignment row. Tickets with no row yet come back
 * as `unassigned` with `version: 0` and a severity-derived priority, so the UI
 * never has to special-case a missing assignment.
 */
export interface Assignment {
	incident_id: string;
	ticket_id: string;
	bus_id: string | null;
	scenario: string | null;
	fault_type: string | null;
	severity: string | null;
	/** The coordinator's diagnostic status, not the workflow state. */
	status: string | null;
	summary: string | null;
	created_at: string;

	work_state: WorkState;
	priority: Priority;
	assignee_id: string | null;
	assignee_name: string | null;
	assignee_initials: string | null;
	due_at: string | null;
	note: string | null;
	version: number;
	updated_at: string | null;
}

export interface AssignmentListResponse {
	items: Assignment[];
	count: number;
}

/** Partial write. `assignee_id: null` unassigns; omitted fields are untouched. */
export interface AssignmentUpdate {
	assignee_id?: string | null;
	work_state?: WorkState;
	priority?: Priority;
	due_at?: string | null;
	note?: string | null;
	/** Send the version you read to get a 409 instead of clobbering someone. */
	expected_version?: number;
}

export interface AssignmentEvent {
	id: string;
	incident_id: string;
	actor_id: string | null;
	actor_name: string | null;
	kind: AssignmentEventKind;
	from_value: string | null;
	to_value: string | null;
	body: string | null;
	created_at: string;
}

export interface AssignmentEventListResponse {
	items: AssignmentEvent[];
	count: number;
}
