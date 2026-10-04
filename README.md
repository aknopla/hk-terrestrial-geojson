# hk-terrestrial-geojson

Hong Kong's land area as a single GeoJSON MultiPolygon, built from the Lands
Department's current 1:5,000 topographic map.

**[See it on a map →](https://aknopla.github.io/hk-terrestrial-geojson/)**
The dataset drawn over a two-colour OpenStreetMap basemap of land and sea.

## Download

Each version is published as a
[GitHub Release](https://github.com/aknopla/hk-terrestrial-geojson/releases)
with both files attached. The newest version is always at:

```
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_terrestrial.geojson
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_terrestrial_2m.geojson
```

To pin a version, replace `latest/download` with `download/<tag>`, for
example `download/v2.0.0`.

## What "terrestrial" means here

Terrestrial means **land**: everything inside Hong Kong's coastline,
including the mainland (Kowloon and the New Territories), Hong Kong Island,
Lantau and the outlying islands. The sea is excluded.

- **Inland water counts as land.** Reservoirs, ponds and fish ponds are
  inside the area, and the polygons have no holes, so a point in the middle
  of a reservoir is on land.
- **Mangroves count as land.** They grow below the high-water mark, so the
  official map draws them over the sea. Here they are land, which takes in
  places such as the Mai Po marshes. Tidal creeks between mangrove patches,
  and bare mudflats, stay sea.

That is the shape you want for "is this place on land in Hong Kong?":
masking the sea on a map, testing whether a coordinate is on land, or
clipping other data to the territory.

This is the land area only, not Hong Kong's jurisdictional boundary, which
also takes in surrounding waters.

## Files

| File | What it is |
|---|---|
| `hk_terrestrial.geojson` | **The dataset**, at the map's full detail. One feature: a MultiPolygon of 823 non-overlapping polygons, 195,189 points, about 1,118.7 km². Minified, 4.8 MB. |
| `hk_terrestrial_2m.geojson` | The same, simplified so no edge moves more than 2 m: 70,652 points, 1.75 MB. For apps and web maps. |
| `sheets.json` | The revision date of each of the 193 map sheets the dataset was built from. |
| `additions.geojson` | Land the official map doesn't show yet, drawn by hand. Currently empty. |
| `build.py` | Downloads the map and builds both datasets. |

All files use WGS 84 longitude/latitude (`EPSG:4326` / `CRS84`), the
GeoJSON default, with coordinates rounded to 7 decimal places (about 1 cm).

## Why this exists instead of the government data

The Lands Department's iB5000 map already has an official land polygon, but
it isn't easy to use as one:

- it comes as 193 separate map sheets in File Geodatabase (FGDB) format,
  about 1.2 GB in total;
- it uses the Hong Kong 1980 Grid rather than longitude/latitude;
- it leaves mangroves on the sea side of the coastline.

This repo turns it into one GeoJSON shape you can drop into a map or an app.

## Source

**iB5000 Digital Topographic Map**, Survey and Mapping Office, Lands
Department, Government of the Hong Kong SAR, published on the
[CSDI Portal](https://portal.csdi.gov.hk/) (dataset
`landsd_rcd_1637224243141_96556`). The map is derived from the 1:1,000
iB1000 database and is revised every two weeks. The sheets used for the
current build were revised between 2025-09-25 and 2026-09-10; `sheets.json`
lists each one.

Land is taken from these iB5000 feature codes:

| Code | Meaning |
|---|---|
| `LAF` | Coastline and land fill: the land polygon, bounded by the high-water mark |
| `PON` `RES` `FEB` `FOU` `SRC` `SRO` `SRP` | Inland water: ponds, reservoirs, filter beds, fountains, service reservoirs |
| `MAN` | Mangrove |

As a check, the `LAF` polygon alone covers 1,114.66 km², against the Lands
Department's published land area of 1,114.57 km². Mangroves outside it add
another 4.04 km².

## Rebuilding

```bash
pip install -r requirements.txt
python build.py
```

`build.py`:

1. reads the sheet index from CSDI, and downloads any sheet that is missing
   from `.cache/` or has been revised since (the first run fetches all
   193);
2. takes the land, inland water and mangrove polygons from every sheet, plus
   `additions.geojson`;
3. combines them into one shape, in the map's own grid, so the sheets join
   exactly;
4. fills any holes, since water enclosed by land counts as land, and drops
   slivers under 1 m²;
5. converts to longitude/latitude, rounds coordinates to about 1 cm, and
   writes both datasets and `sheets.json`.

To add land the map doesn't show yet, draw a polygon in `additions.geojson`.
It only has to cover the missing land; it can overlap the coastline freely,
because the build combines everything.

## Licence

This repo uses the same terms as its source. See [LICENSE.md](LICENSE.md).
In short: the data may be used, copied and redistributed, commercially or
not, under the
[CSDI Portal Terms and Conditions of Use](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC),
crediting the Government of the Hong Kong SAR and the CSDI Portal as the
source. It comes with no warranty.
