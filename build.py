"""Build hk_terrestrial.geojson from the Lands Department's iB5000 map.

    pip install -r requirements.txt
    python build.py

Downloads the 193 iB5000 sheets into .cache/ (about 1.2 GB; only sheets
that are missing or have been revised are fetched again), then writes
hk_terrestrial.geojson, hk_terrestrial_2m.geojson and sheets.json.
"""

import json
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyogrio
import pyproj
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import transform, unary_union

TILE_INDEX = (
    "https://portal.csdi.gov.hk/csdi-webpage/file-api"
    "?dataset_id=landsd_rcd_1637224243141_96556&format=geojson&layer_name=TileIndex"
)
CACHE = Path(".cache/ib5000")
OUTPUT = "hk_terrestrial.geojson"
OUTPUT_LIGHT = "hk_terrestrial_2m.geojson"
MANIFEST = "sheets.json"

# What counts as land. iB5000 codes, from its data dictionary:
#   LAF            Coastline And LandFill: the land polygon, bounded by the
#                  high-water mark
#   PON RES FEB    pond / pool, reservoir, filter bed,
#   FOU SRC SRO    fountain, service reservoirs: inland water, which counts
#   SRP            as land
#   MAN            mangrove: grows below the high-water mark, so the map puts
#                  it on the sea; it counts as land here
LAND_CODES = ("LAF", "PON", "RES", "FEB", "FOU", "SRC", "SRO", "SRP")
MANGROVE_CODES = ("MAN",)

MIN_PART_M2 = 1.0  # drops slivers; the smallest real islets are larger
LIGHT_SIMPLIFY_M = 2.0  # metres; the light file stays within this of the full one
DECIMALS = 7  # about 1 cm

TO_WGS84 = pyproj.Transformer.from_crs(2326, 4326, always_xy=True).transform


def fetch_index():
    with urllib.request.urlopen(TILE_INDEX, timeout=120) as r:
        features = json.load(r)["features"]
    return {f["properties"]["SHEETNO"]: f["properties"] for f in features}


def is_valid_zip(path):
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def download(sheet, props):
    """Fetch a sheet unless the cache already holds its current revision."""
    path = CACHE / f"{sheet}.zip"
    revision = CACHE / f"{sheet}.revision"
    if revision.exists() and revision.read_text() == props["REVISIONDATE"] and path.exists():
        return sheet, "cached"
    part = path.with_suffix(".part")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(props["FGDB"], timeout=900) as r, open(part, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if is_valid_zip(part):
                part.replace(path)
                revision.write_text(props["REVISIONDATE"])
                return sheet, "downloaded"
        except OSError:
            pass
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not download sheet {sheet}")


def read(sheet, layer, codes):
    gdb = f"/vsizip/{CACHE / sheet}.zip/{sheet}/{sheet}.gdb"
    where = "FEATURECODE IN (%s)" % ",".join(f"'{c}'" for c in codes)
    # The filter column has to be read for the filter to apply.
    _, _, geometry, _ = pyogrio.raw.read(gdb, layer=layer, columns=["FEATURECODE"], where=where)
    return [shapely.force_2d(shapely.from_wkb(g)) for g in geometry if g is not None]


def polygons(geom):
    """The polygon parts of a geometry, dropping any lines or points."""
    if geom.geom_type == "Polygon":
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in polygons(g)]
    return []


def rounded(c):
    return [rounded(x) for x in c] if isinstance(c, (list, tuple)) else round(c, DECIMALS)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    index = fetch_index()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for sheet, status in pool.map(lambda s: download(s, index[s]), sorted(index)):
            if status == "downloaded":
                print(f"downloaded {sheet}", file=sys.stderr)

    # Work in the map's own grid (EPSG:2326, metres): sheets join exactly and
    # thresholds are in metres. Convert to longitude/latitude once, at the end.
    pieces = []
    for sheet in sorted(index):
        pieces += read(sheet, "HydrographyPoly", LAND_CODES)
        pieces += read(sheet, "LandCoverPoly", MANGROVE_CODES)
    land = unary_union([p for g in pieces for p in polygons(shapely.make_valid(g))])

    # Fill every hole (water enclosed by land counts as land) and drop
    # slivers. Repeat, since filling can make parts touch and enclose a gap.
    while True:
        merged = unary_union([Polygon(p.exterior) for p in polygons(land) if p.area >= MIN_PART_M2])
        if merged.equals(land):
            break
        land = merged

    write(land, OUTPUT)
    write(land.simplify(LIGHT_SIMPLIFY_M, preserve_topology=True), OUTPUT_LIGHT)
    with open(MANIFEST, "w") as f:
        json.dump({s: index[s]["REVISIONDATE"] for s in sorted(index)}, f, indent=0)
        f.write("\n")


def write(land, path):
    """Write land (in the map's grid) as a one-feature GeoJSON in WGS 84."""
    area_km2 = land.area / 1e6
    land = shapely.set_precision(transform(TO_WGS84, land), 10**-DECIMALS)
    land = MultiPolygon(polygons(shapely.orient_polygons(land)))  # RFC 7946 winding
    assert land.is_valid, shapely.is_valid_reason(land)

    geometry = mapping(land)
    geometry["coordinates"] = rounded(geometry["coordinates"])
    with open(path, "w") as f:
        json.dump(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": geometry}],
            },
            f,
            separators=(",", ":"),
        )
    print(
        f"{path}: {len(land.geoms)} polygons, "
        f"{shapely.get_num_coordinates(land)} points, {area_km2:.2f} km²"
    )


if __name__ == "__main__":
    main()
