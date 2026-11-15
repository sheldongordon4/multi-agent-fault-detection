# MAFD operator console

React + TypeScript + Vite front end for the fault-detection pipeline. Vite 8,
React 19, Tailwind v4, shadcn/Radix, TanStack Query (server state), Zustand (UI
state), MapLibre GL (map).

```
src/
  app/           routes, layouts, store (zustand slices)
  features/
    incidents/   the map screen: list sheet, incident detail renderer
    map/         basemap + grid overlay (own module — not owned by incidents)
    overview/    stat tiles, live signal chart, fault-type chart
    assignments/ ticket ownership: table + shared detail panel
  shared/        ui primitives, hooks, lib
public/map/      the offline basemap assets — see below
```

**Three pages.** `/overview` is the landing page — `/` redirects to it, because
it answers "how is the grid right now", which is the question an operator
arrives with (stat tiles, live signal, fault types). It was briefly a bottom
drawer on the map, which stacked a thing you read on a thing you operate.
`/incidents` is the map screen — map-first, with a collapsible incident list
and a floating detail panel. `/assignments` is the ticket-ownership page: a
filterable table and a detail sheet. It had a dnd-kit kanban board beside the
table, behind a Board/Table toggle; **the board is gone** — the table did the
same writes, kept working at storm volume, and was the keyboard-accessible
one, so the board was a second way to do one thing. The `@dnd-kit/core`
dependency went with it.

**`AssignmentDetailPanel` is shared, and it is the only place a ticket's detail
is defined.** The assignments sheet and the map's floating panel render the same
component, so a fault can be assigned without leaving the map. It fetches by
incident id and takes its height from its parent — don't give it
viewport-relative sizing or a second copy. Its `defaultTab` differs by page on
purpose: `/assignments` opens on **Work** because it exists to move work along,
the map opens on **Diagnosis** because the first question about a pin is what
the coordinator made of it.

**The bus selector belongs to the live signal chart**, not to the overview page
header. From the header it read as a page-wide filter, which it never was — the
stat tiles and fault-type chart cover every bus regardless.

---

## The map

Everything is **self-hosted and works offline** — no API keys, no tile server, no
runtime calls to a third party. That's deliberate: a control-room tool shouldn't
stop working because someone else's service is down, and grid data shouldn't leave
the premises.

### Assets in `public/map/` (do not delete — these *are* the basemap)

| File | What it is |
| --- | --- |
| `jamaica.pmtiles` | 13 MB vector basemap, Jamaica only, zoom 0–14 |
| `fonts/` | Noto Sans glyph ranges — without these, no map labels render |
| `jamaica-parishes.geojson` | 14 parish polygons (43 KB) for the fault shading |

`.pmtiles` is a single static file read by the browser over HTTP range requests
(`pmtiles://` protocol), so any static host works — no tile server process.

### Where the bus pins come from

`features/map/utils/bus-locations.ts` is the **only** place bus geography lives.
The town coordinates are real; the bus → town assignment is **invented**, because
JPS grid topology isn't public and nothing here is an actual substation site.
Replace `lat`/`lng`/`name`/`parish` when you have real values — `parish` must
match a `parish` in `jamaica-parishes.geojson`, which is what drives the fault
shading. `FEEDER_EDGES` in the same file is *not* invented: it's the published
IEEE 13-node radial topology, so the lines are true while the geography is
placeholder.

Only IEEE13 ids (`b6xx`) can ever match an incident — the streaming path still
uses `bus_1/2/3`, which is the unreconciled namespace split tracked in
`docs/System_Architecture.md` §16.

### Regenerating the basemap

```bash
go install github.com/protomaps/go-pmtiles@latest

# Extracts ONLY Jamaica's bbox from the planet build via range requests —
# it downloads ~14 MB, not the 114 GB planet.
go-pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles \
  frontend/public/map/jamaica.pmtiles \
  --bbox=-78.9,17.3,-75.6,19.0 --maxzoom=14
```

Current build dates: `https://build-metadata.protomaps.dev/builds.json`.
Glyphs come from `https://protomaps.github.io/basemaps-assets/fonts/`.

### Licensing (short version)

The **software** is permissive — MapLibre, pmtiles and `@protomaps/basemaps` are
BSD-3-Clause, react-map-gl is MIT. The **data** is OpenStreetMap under **ODbL**,
which requires **attribution** — the `© OpenStreetMap contributors` control must
stay visible. Parish polygons are geoBoundaries (CC-BY). Noto Sans is SIL OFL.

ODbL share-alike applies to derived *databases*, not to maps you display: drawing
your substations on top does **not** make your grid data ODbL.

Do not point production at `tile.openstreetmap.org` — that's donated
infrastructure with a usage policy, and there is no licence you can buy for it.
Self-hosting is the supported path.

### Online mode

`VITE_MAP_MODE=online` swaps the basemap for OSM raster tiles. Useful for a quick
look; **offline is the default and the shippable one.**

---

## Gotchas worth knowing before you change things

- **`maplibre-gl` must stay pre-bundled.** It loads its tile-parsing worker as a
  separate file; excluding it from `optimizeDeps` "fixes" the missing worker but
  makes Vite transform 550 KB on every dev-server start (~67s, and it starves
  lazy route chunks). Instead the worker URL is set explicitly in
  `features/map/utils/basemap.ts`.
- **`reuseMaps` means `onLoad` may never fire.** A pooled map instance has
  already emitted `load`, so anything gated on it silently never runs. Use
  `onIdle`/`onStyleData`, or check imperatively.
- **Camera padding shifts, `fitBounds` re-frames.** `setPadding` keeps the island
  clear of the floating panels without touching zoom; `fitBounds` recomputes zoom
  too, so it runs only on first mount — otherwise every panel toggle would throw
  away the operator's zoom. Never pass the same padding to both; they compound.
- **The dev server needs polled file watching in Docker** (inotify doesn't cross
  the Windows bind mount) — and the ignore list is load-bearing: it *replaces*
  Vite's defaults, so `node_modules`, `dist` and `.pnpm-store` must be listed
  explicitly or the watcher pegs a CPU and starves the server.
- **`pnpm add` on the host doesn't reach the container** — its `node_modules` is a
  named volume. Run `docker compose -f docker-compose.dev.yaml exec -e CI=true client pnpm install`.
- **ESLint currently can't run**: `typescript-eslint` doesn't support TypeScript 7.
  `npx tsc -b` is the working check.

## Scripts

```bash
pnpm dev       # dev server (or the `client` service in docker-compose.dev.yaml)
pnpm build     # tsc -b && vite build
pnpm preview   # serve the production build
```
