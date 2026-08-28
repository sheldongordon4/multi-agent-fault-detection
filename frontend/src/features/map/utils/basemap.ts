import { layers, namedFlavor } from '@protomaps/basemaps';
import { addProtocol, setWorkerUrl, type StyleSpecification } from 'maplibre-gl';
// MapLibre parses vector tiles in a web worker that it normally locates relative
// to its own bundle. Once Vite pre-bundles maplibre-gl into .vite/deps, that
// relative lookup points at a file the optimizer never emitted, so tiles silently
// never parse. Letting Vite build the worker (?worker&url resolves its internal
// imports too) and handing MapLibre the resulting URL fixes it at the source —
// without opting maplibre-gl out of pre-bundling, which cost ~67s per cold start.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Protocol } from 'pmtiles';

setWorkerUrl(maplibreWorkerUrl);

// The grid map has two interchangeable basemaps behind the SAME map instance and
// the SAME overlay code — only the style source differs:
//
//   online  -> keyless OpenStreetMap raster tiles (whole world, view fenced to
//              Jamaica). Needs the internet; good for a quick look.
//   offline -> a self-hosted Jamaica-only .pmtiles vector archive + local glyphs,
//              themed with the editable Protomaps base layers. Zero network calls
//              at runtime — works on an air-gapped control-room machine.
//
// Switch with VITE_MAP_MODE=online|offline (defaults to offline, since the local
// archive ships with the app).

export type MapMode = 'online' | 'offline';

export const MAP_MODE: MapMode =
	import.meta.env.VITE_MAP_MODE === 'online' ? 'online' : 'offline';

// --- online basemap -------------------------------------------------------

const OSM_STYLE: StyleSpecification = {
	version: 8,
	sources: {
		osm: {
			type: 'raster',
			tiles: [
				'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
				'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
				'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
			],
			tileSize: 256,
			attribution: '© OpenStreetMap contributors',
		},
	},
	layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
};

// --- offline basemap ------------------------------------------------------

// Register the pmtiles:// protocol once so MapLibre can read the local .pmtiles
// archive directly via HTTP range requests — no tile server involved.
let pmtilesRegistered = false;
function ensurePmtilesProtocol() {
	if (pmtilesRegistered) return;
	const protocol = new Protocol();
	addProtocol('pmtiles', protocol.tile);
	pmtilesRegistered = true;
}

// Deliberately DESATURATED flavors, not the stock 'light'/'dark'.
//
// This is an operator display: the only saturated things on screen should be
// fault status (red / amber / green). Protomaps' stock 'light' paints water
// #80deea — a vivid cyan that competes with an alarm marker for attention. These
// two flavors are fully neutral greys (earth #cccccc / #141414), so the basemap
// recedes and the overlay reads instantly.
const FLAVOR_BY_THEME = {
	light: 'grayscale',
	dark: 'black',
} as const;

export type ResolvedTheme = keyof typeof FLAVOR_BY_THEME;

function offlineStyle(theme: ResolvedTheme): StyleSpecification {
	// Absolute URL so the pmtiles protocol can resolve the file; the archive and
	// glyphs are served by Vite from frontend/public/map/.
	const pmtilesUrl = `pmtiles://${window.location.origin}/map/jamaica.pmtiles`;

	return {
		version: 8,
		glyphs: '/map/fonts/{fontstack}/{range}.pbf',
		sources: {
			// `protomaps` is the source name the generated layers reference.
			protomaps: {
				type: 'vector',
				url: pmtilesUrl,
				attribution: '© OpenStreetMap contributors',
			},
		},
		// Fork these layers to restyle any colour/label — this is the control
		// surface for the whole basemap's appearance.
		layers: layers('protomaps', namedFlavor(FLAVOR_BY_THEME[theme]), {
			lang: 'en',
		}),
	};
}

// Cache per theme for the lifetime of the page. The Overview route is lazy-loaded,
// so navigating away and back remounts <GridMap>; handing MapLibre a NEW style
// object each time makes it tear the whole style down and reload it (the grey
// flash). Stable references let `reuseMaps` actually reuse the map, while still
// allowing a genuine theme switch to swap styles.
const styleCache = new Map<ResolvedTheme, StyleSpecification>();

/** Returns the basemap style for the active mode/theme, registering pmtiles if needed. */
export function getBasemapStyle(theme: ResolvedTheme): StyleSpecification {
	// Online mode is a single raster style; theme doesn't apply to it.
	if (MAP_MODE === 'online') return OSM_STYLE;

	const cached = styleCache.get(theme);
	if (cached) return cached;

	ensurePmtilesProtocol();
	const style = offlineStyle(theme);
	styleCache.set(theme, style);
	return style;
}
