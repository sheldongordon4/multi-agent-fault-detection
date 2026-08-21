# Offline basemap assets

These files **are** the map. Deleting them leaves a blank grey canvas — they are
not build output and are not regenerated automatically.

| File | Source | Licence |
| --- | --- | --- |
| `jamaica.pmtiles` | Protomaps planet build, Jamaica bbox only | Data: **ODbL** (OpenStreetMap) |
| `jamaica-parishes.geojson` | geoBoundaries JAM ADM1 | **CC-BY** |
| `fonts/Noto Sans *` | protomaps/basemaps-assets | **SIL OFL 1.1** |

Details:

- `jamaica.pmtiles` — 13 MB, zoom 0–14, bbox `-78.9,17.3,-75.6,19.0`, extracted
  from the `20260813` planet build. Regeneration command in `frontend/README.md`.
- `fonts/` — Noto Sans Regular / Medium / Italic, ranges `0-255` and `256-511`.
  Without these the map renders **no labels at all**.

## Attribution is required

ODbL obliges attribution: the `© OpenStreetMap contributors` control rendered by
MapLibre must stay visible. Don't hide it or let a floating panel cover it.

Share-alike applies to derived *databases*, not to displayed maps — overlaying
substations and incidents does not make your grid data ODbL.

## Don't point production at a public tile server

`tile.openstreetmap.org` is donated infrastructure with a usage policy, and there
is no licence you can purchase for it. Self-hosting these files is the supported
path and the reason the console works with no internet.
