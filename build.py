"""Build hk_terrestrial.geojson from the Lands Department's iB5000 map, and
hk_boundary.geojson from the Home Affairs Department's district boundaries.

    pip install -r requirements.txt
    python build.py             # everything
    python build.py land        # only the land files and the sea mask
    python build.py boundary    # only the boundary

Either way, the figures in README.md and index.html are then refreshed from
the files on disk.

The land target downloads the 193 iB5000 sheets into .cache/ (about 1.2 GB;
only sheets that are missing or have been revised are fetched again), then
writes hk_terrestrial.geojson, hk_terrestrial_2m.geojson, hk_sea_mask.geojson
and sheets.json. The boundary target downloads one file of under 1 MB and
writes hk_boundary.geojson.
"""

import argparse
import gzip
import json
import re
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
OUTPUT_MASK = "hk_sea_mask.geojson"
MANIFEST = "sheets.json"
# Hong Kong's land is about 1,119 km². A build outside this range means the
# source changed shape and needs a look.
LAND_KM2 = (1100, 1140)

# Hong Kong's 18 districts, land and sea, from the Home Affairs Department
# (DATA.GOV.HK dataset hk-had-json1-hong-kong-administrative-boundaries).
# Together they cover the whole HKSAR, so their union is its boundary.
DISTRICTS = (
    "https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/"
    "hksar_18_district_boundary.json"
)
OUTPUT_BOUNDARY = "hk_boundary.geojson"
# The HKSAR's published total area, land and sea, is about 2,755 km². A union
# outside this range means the source changed shape and needs a look.
BOUNDARY_KM2 = (2750, 2760)

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
MASK_DECIMALS = 6  # about 10 cm; plenty for a shape already within 2 m

# The mask is this rectangle with every piece of land cut out as a hole.
WORLD = [(-180, -90), (180, -90), (180, 90), (-180, 90), (-180, -90)]

TO_WGS84 = pyproj.Transformer.from_crs(2326, 4326, always_xy=True).transform
TO_GRID = pyproj.Transformer.from_crs(4326, 2326, always_xy=True).transform


def fetch_index():
    """Each sheet's properties, with its outline (WGS 84) as "geometry"."""
    with urllib.request.urlopen(TILE_INDEX, timeout=120) as r:
        features = json.load(r)["features"]
    return {f["properties"]["SHEETNO"]: {**f["properties"], "geometry": f["geometry"]} for f in features}


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


def rounded(c, decimals):
    return [rounded(x, decimals) for x in c] if isinstance(c, (list, tuple)) else round(c, decimals)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "targets", nargs="*", choices=["land", "boundary"],
        help="what to build (default: everything)",
    )
    targets = parser.parse_args().targets or ["land", "boundary"]
    if "land" in targets:
        build_land()
    if "boundary" in targets:
        build_boundary()
    update_docs()


def build_land(index=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    index = index or fetch_index()
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

    area_km2 = land.area / 1e6
    low, high = LAND_KM2
    assert low <= area_km2 <= high, f"land is {area_km2:.2f} km², expected {low}–{high}"

    light = land.simplify(LIGHT_SIMPLIFY_M, preserve_topology=True)
    write(land, OUTPUT)
    write(light, OUTPUT_LIGHT)
    write_mask(light, OUTPUT_MASK)
    with open(MANIFEST, "w") as f:
        json.dump({s: index[s]["REVISIONDATE"] for s in sorted(index)}, f, indent=0)
        f.write("\n")


def build_boundary():
    """Write the HKSAR boundary, land and sea: the union of its 18 districts."""
    with urllib.request.urlopen(DISTRICTS, timeout=120) as r:
        districts = json.load(r)["features"]
    assert len(districts) == 18, f"expected 18 districts, got {len(districts)}"

    # Union in the grid, so the gap and area thresholds are in metres.
    parts = [transform(TO_GRID, shapely.geometry.shape(d["geometry"])) for d in districts]
    union = unary_union([p for g in parts for p in polygons(shapely.make_valid(g))])
    # Neighbouring districts can leave hairline gaps or slivers along shared
    # edges; the territory itself has no holes and is one piece.
    pieces = [Polygon(p.exterior) for p in polygons(union) if p.area >= MIN_PART_M2]
    assert len(pieces) == 1, f"expected one polygon, got {len(pieces)}"
    boundary = pieces[0]

    area_km2 = boundary.area / 1e6
    low, high = BOUNDARY_KM2
    assert low <= area_km2 <= high, f"boundary is {area_km2:.2f} km², expected {low}–{high}"

    boundary = shapely.set_precision(transform(TO_WGS84, boundary), 10**-DECIMALS)
    boundary = shapely.orient_polygons(boundary)  # RFC 7946 winding
    dump(boundary, OUTPUT_BOUNDARY, DECIMALS)
    print(
        f"{OUTPUT_BOUNDARY}: 1 polygon, "
        f"{shapely.get_num_coordinates(boundary)} points, {area_km2:.2f} km²"
    )


def write(land, path):
    """Write land (in the map's grid) as a one-feature GeoJSON in WGS 84."""
    area_km2 = land.area / 1e6
    land = shapely.set_precision(transform(TO_WGS84, land), 10**-DECIMALS)
    land = MultiPolygon(polygons(shapely.orient_polygons(land)))  # RFC 7946 winding
    dump(land, path, DECIMALS)
    print(
        f"{path}: {len(land.geoms)} polygons, "
        f"{shapely.get_num_coordinates(land)} points, {area_km2:.2f} km²"
    )


def write_mask(land, path):
    """Write everything except land: the world with each land polygon as a hole.

    For dimming a map outside Hong Kong: a renderer can't invert a polygon,
    so the inverse is prebuilt here.
    """
    land = shapely.set_precision(transform(TO_WGS84, land), 10**-MASK_DECIMALS)
    holes = [p.exterior.coords for p in polygons(land)]
    mask = shapely.orient_polygons(Polygon(WORLD, holes))  # RFC 7946 winding
    dump(mask, path, MASK_DECIMALS)
    print(f"{path}: {len(holes)} holes, {shapely.get_num_coordinates(mask)} points")


def dump(geometry, path, decimals):
    """Write a geometry as a one-feature GeoJSON FeatureCollection."""
    assert geometry.is_valid, shapely.is_valid_reason(geometry)
    geojson = mapping(geometry)
    geojson["coordinates"] = rounded(geojson["coordinates"], decimals)
    with open(path, "w") as f:
        json.dump(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": geojson}],
            },
            f,
            separators=(",", ":"),
        )


def read_geometry(path):
    """The geometry of a one-feature GeoJSON file written by dump()."""
    with open(path) as f:
        return shapely.geometry.shape(json.load(f)["features"][0]["geometry"])


def update_docs():
    """Refresh the figures in README.md and index.html from the files on disk."""
    files = (OUTPUT, OUTPUT_LIGHT, OUTPUT_MASK, OUTPUT_BOUNDARY)
    data = {path: Path(path).read_bytes() for path in files}
    geometry = {path: read_geometry(path) for path in files}
    land, light, mask, boundary = (geometry[path] for path in files)

    def km2(g):
        return f"{transform(TO_GRID, g).area / 1e6:,.2f} km²"

    rows = {
        "**Size**": [f"**{size(len(data[p]))}**" for p in files],
        "Gzipped": [size(len(gzip.compress(data[p]))) for p in files],
        "Points": [f"{shapely.get_num_coordinates(geometry[p]):,}" for p in files],
        "Shape": [
            f"{len(land.geoms)} land polygons",
            f"{len(light.geoms)} land polygons",
            f"the world, with {len(mask.interiors)} land holes",
            "one polygon, no holes",
        ],
        "Area": [km2(land), km2(light), "(everything else)", km2(boundary)],
    }
    with open(MANIFEST) as f:
        dates = sorted(json.load(f).values())
    first, last = (f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in (dates[0], dates[-1]))

    readme = Path("README.md").read_text()
    for label, cells in rows.items():
        readme = replace_once(rf"(?m)^\| {re.escape(label)} \|.*$", f"| {label} | {' | '.join(cells)} |", readme)
    readme = replace_once(
        r"revised between \d{4}-\d\d-\d\d and \d{4}-\d\d-\d\d",
        f"revised between {first} and {last}",
        readme,
    )
    Path("README.md").write_text(readme)

    page = Path("index.html").read_text()
    for value, path in (("full", OUTPUT), ("2m", OUTPUT_LIGHT)):
        page = replace_once(
            rf'(data-value="{value}">[^<]*<span>)[^<]*(</span>)',
            rf"\g<1>{size(len(data[path]))}\g<2>",
            page,
        )
    Path("index.html").write_text(page)


def replace_once(pattern, replacement, text):
    text, n = re.subn(pattern, replacement, text)
    assert n == 1, f"expected one match for {pattern!r}, got {n}"
    return text


def size(n):
    """A file size as written in the README: 4.84 MB, 1.3 MB, 59 KB."""
    if n < 100_000:
        return f"{n / 1000:.0f} KB"
    return f"{n / 1e6:.2f}".rstrip("0").rstrip(".") + " MB"


if __name__ == "__main__":
    main()
