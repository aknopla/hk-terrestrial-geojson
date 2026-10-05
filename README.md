# hk-terrestrial-geojson

Hong Kong's land area as a single GeoJSON MultiPolygon, built from the Lands
Department's current 1:5,000 topographic map. Alongside it, the HKSAR's
boundary, land and sea, as one Polygon.

**[See it on a map →](https://aknopla.github.io/hk-terrestrial-geojson/)**
The land drawn over a two-colour OpenStreetMap basemap of land and sea, or
over the Lands Department's aerial imagery, at either level of detail, with
the boundary as a dashed line.

## Download

Each version is published as a
[GitHub Release](https://github.com/aknopla/hk-terrestrial-geojson/releases)
with four files attached. The first two are the land itself; the 2 m file
trades a little edge detail for a third of the size. The sea mask is the
same land turned inside out. The boundary is the whole territory, land and
sea.

| | `hk_terrestrial.geojson` | `hk_terrestrial_2m.geojson` | `hk_sea_mask.geojson` | `hk_boundary.geojson` |
|---|---:|---:|---:|---:|
| **Size** | **4.8 MB** | **1.75 MB** | **1.6 MB** | **59 KB** |
| Gzipped | 1.3 MB | 0.5 MB | 0.42 MB | 17 KB |
| Points | 195,189 | 70,652 | 70,653 | 2,386 |
| Shape | 823 land polygons | 823 land polygons | the world, with 823 land holes | one polygon, no holes |
| Area | 1,118.73 km² | 1,118.69 km² | (everything else) | 2,755.11 km² |
| Detail | the map's full detail | every edge within 2 m of the full file | the 2 m shape, coordinates to about 10 cm | the Home Affairs Department's district boundaries |
| Use it for | analysis, precise land/sea tests | apps and web maps | dimming or hiding a map outside Hong Kong | "is this in Hong Kong at all?", keeping a map on Hong Kong |

A map renderer can't fill "everything except a polygon", so the sea mask
does the inverting for you: draw it as a fill and everything outside Hong
Kong's land is covered.

The newest version is always at:

```
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_terrestrial.geojson
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_terrestrial_2m.geojson
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_sea_mask.geojson
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/hk_boundary.geojson
https://github.com/aknopla/hk-terrestrial-geojson/releases/latest/download/SHA256SUMS
```

`SHA256SUMS` lists each file's checksum, for verifying a download.

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

The land files are the land area only. For Hong Kong's jurisdictional
boundary, which also takes in the surrounding waters, use
`hk_boundary.geojson`.

## The boundary

`hk_boundary.geojson` is the HKSAR's boundary: the area the Hong Kong
government administers, land and sea, as one Polygon with no holes. In the
north it follows the Shenzhen River and the middle of Deep Bay; elsewhere it
runs through open water, out to the sea boundary set when the HKSAR was
established (State Council Order No. 221, 1997).

It is the union of the Home Affairs Department's 18 district boundaries,
which between them cover the whole territory. Its area, 2,755.11 km², matches
the HKSAR's published total area of land and sea. Redrawing a district
boundary moves lines inside it; the outer edge has not moved since 1997.

Use it to decide whether a point is anywhere in Hong Kong, sea included, or
to keep a map from wandering away from Hong Kong. For land versus sea, use
the land files.

## Files

| File | What it is |
|---|---|
| `hk_terrestrial.geojson` | **The dataset**, at the map's full detail: one feature, a MultiPolygon of non-overlapping polygons. |
| `hk_terrestrial_2m.geojson` | The same, simplified so no edge moves more than 2 m. |
| `hk_sea_mask.geojson` | The 2 m shape inverted: one Polygon covering the world, with each piece of land as a hole. |
| `hk_boundary.geojson` | The HKSAR boundary, land and sea: one Polygon. |
| `sheets.json` | The revision date of each of the 193 map sheets the dataset was built from. |
| `build.py` | Downloads the sources and builds all four files. |

All files use WGS 84 longitude/latitude (`EPSG:4326` / `CRS84`), the
GeoJSON default. The land files and the boundary round coordinates to 7
decimal places (about 1 cm); the sea mask to 6 (about 10 cm).

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

The boundary comes from the **Hong Kong Administrative Boundaries** dataset
of the Home Affairs Department, Government of the Hong Kong SAR, published on
[DATA.GOV.HK](https://data.gov.hk/en-data/dataset/hk-had-json1-hong-kong-administrative-boundaries)
(`hksar_18_district_boundary.json`, already in longitude/latitude).

## Rebuilding

```bash
pip install -r requirements.txt
python build.py             # everything
python build.py land        # only the land files and the sea mask
python build.py boundary    # only the boundary
```

For the land, `build.py`:

1. reads the sheet index from CSDI, and downloads any sheet that is missing
   from `.cache/` or has been revised since (the first run fetches all
   193);
2. takes the land, inland water and mangrove polygons from every sheet;
3. combines them into one shape, in the map's own grid, so the sheets join
   exactly;
4. fills any holes, since water enclosed by land counts as land, and drops
   slivers under 1 m²;
5. converts to longitude/latitude, rounds coordinates, and writes the three
   files and `sheets.json`.

For the boundary, it downloads the 18 districts, merges them in the map's
grid, drops any sliver under 1 m² left along shared edges, checks that the
result is one polygon of 2,750–2,760 km², and writes it.

## Releasing

```bash
python build.py
git commit -am "…" && git push
shasum -a 256 hk_terrestrial.geojson hk_terrestrial_2m.geojson hk_sea_mask.geojson hk_boundary.geojson > SHA256SUMS
gh release create vX.Y.Z hk_terrestrial.geojson hk_terrestrial_2m.geojson hk_sea_mask.geojson hk_boundary.geojson SHA256SUMS
```

Apps that vendor a file can watch the releases and check the download
against `SHA256SUMS`.

## Licence

This repo uses the same terms as its sources. See [LICENSE.md](LICENSE.md).
In short: the data may be used, copied and redistributed, commercially or
not, under the
[CSDI Portal Terms and Conditions of Use](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC)
(the land files and the sea mask) and the
[DATA.GOV.HK Terms and Conditions of Use](https://data.gov.hk/en/terms-and-conditions)
(the boundary), crediting the Government of the Hong Kong SAR and the portal
as the source. It comes with no warranty.
