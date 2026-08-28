/**
 * Where each monitored bus sits on the map.
 *
 * PLACEHOLDER LOCATIONS — the town coordinates are real, but the bus -> town
 * assignment is invented. JPS grid topology is not public, so nothing here is an
 * actual substation location. Replace `lat`/`lng`/`name`/`parish` with real values
 * when you have them; nothing else needs to change.
 *
 * NAMESPACE: these are the IEEE13 feeder buses used by the EVENT path
 * (scripts/produce_events.py -> feeder.events -> detection -> faulttickets), which
 * is what stamps `bus_id` on a FaultTicket. That is deliberately NOT the same set
 * as the streaming path (scripts/produce_signals.py -> raw.signals), which uses
 * bus_1/bus_2/bus_3 and drives the Live Signal chart. Only these IDs can ever
 * match an incident, so these are the ones worth putting on a fault map.
 *
 * This is the ONLY place location lives. When the backend grows a substations
 * table, delete this file and fetch the same shape instead.
 */

export interface BusLocation {
	busId: string;
	/** Display name for the site. */
	name: string;
	/** Parish name — must match `parish` in jamaica-parishes.geojson. */
	parish: string;
	lat: number;
	lng: number;
}

export const BUS_LOCATIONS: BusLocation[] = [
	{
		busId: 'b650',
		name: 'Kingston',
		parish: 'Kingston',
		lat: 17.9714,
		lng: -76.7931,
	},
	{
		busId: 'b632',
		name: 'Spanish Town',
		parish: 'Saint Catherine',
		lat: 17.9911,
		lng: -76.9574,
	},
	{
		busId: 'b671',
		name: 'Mandeville',
		parish: 'Manchester',
		lat: 18.0416,
		lng: -77.5072,
	},
	{
		busId: 'b675',
		name: 'Montego Bay',
		parish: 'Saint James',
		lat: 18.4762,
		lng: -77.8939,
	},
	{
		busId: 'b684',
		name: 'Ocho Rios',
		parish: 'Saint Ann',
		lat: 18.4076,
		lng: -77.103,
	},
];

const BY_ID = new Map(BUS_LOCATIONS.map((b) => [b.busId, b]));

export function getBusLocation(busId: string): BusLocation | undefined {
	return BY_ID.get(busId);
}

/**
 * Feeder connectivity between the mapped buses.
 *
 * Unlike the coordinates above, this is NOT invented: the IEEE 13-node test
 * feeder is a published standard case and these are its real radial connections,
 * with unmapped intermediate nodes collapsed:
 *
 *   650 ──▶ 632 ──▶ 671 ──┬──▶ 684
 *                          └──▶ 675   (via 692)
 *
 * So the topology is true while the geography is placeholder — the lines show
 * which bus feeds which, not where any cable physically runs.
 */
export const FEEDER_EDGES: [string, string][] = [
	['b650', 'b632'],
	['b632', 'b671'],
	['b671', 'b684'],
	['b671', 'b675'],
];
