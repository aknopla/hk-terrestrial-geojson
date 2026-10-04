"""Build hk_terrestrial.geojson from CEDD's coastline plus additions.geojson.

    pip install 'shapely>=2.1'
    python merge.py
"""

import json
import math

import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform, unary_union

SOURCE = "cedd_coastline.geojson"
ADDITIONS = "additions.geojson"
OUTPUT = "hk_terrestrial.geojson"

GRID = 1e-7  # degrees, about 1 cm; source digits beyond this are noise
SEAM = 3 / 111_000  # degrees, about 3 m; closes gaps under ~6 m wide
MIN_PART_M2 = 10  # the smallest real island in the source is ~200 m²

# Local metres at Hong Kong's latitude, for area thresholds only.
_KX = 111_320 * math.cos(math.radians(22.35))
_KY = 110_574


def area_m2(geom):
    return transform(lambda x, y, z=None: (x * _KX, y * _KY), geom).area


def polygons(geom):
    """The polygon parts of a geometry, dropping any lines or points."""
    if geom.geom_type == "Polygon":
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in polygons(g)]
    return []


def load(path):
    features = json.load(open(path))["features"]
    # make_valid repairs self-intersecting rings; CEDD has 14 invalid polygons.
    return [
        p
        for f in features
        if f["geometry"] and f["geometry"]["coordinates"]
        for p in polygons(shapely.make_valid(shape(f["geometry"])))
    ]


source = load(SOURCE)
additions = load(ADDITIONS)
land = unary_union(source + additions)

# Close narrow gaps where an addition meets the source coastline; they render
# as seams. Only near the additions' edges, so the surveyed coastline keeps its
# narrow inlets.
near_additions = unary_union([a.boundary for a in additions]).buffer(10 * SEAM)
closed = land.buffer(SEAM, join_style="mitre").buffer(-SEAM, join_style="mitre")
land = unary_union([land, closed.difference(land).intersection(near_additions)])

# Drop slivers left by self-intersecting rings and fill every hole: neither
# input has a real one, so each is a gap between an addition and the
# coastline. Repeat, since filling can make parts touch and enclose a new gap.
land = shapely.set_precision(land, GRID)
while True:
    parts = [Polygon(p.exterior) for p in polygons(land) if area_m2(p) >= MIN_PART_M2]
    merged = shapely.set_precision(unary_union(parts), GRID)
    if merged.equals(land):
        break
    land = merged

land = MultiPolygon(polygons(shapely.orient_polygons(land)))  # RFC 7946 winding
assert land.is_valid, shapely.is_valid_reason(land)


def rounded(c):
    return [rounded(x) for x in c] if isinstance(c, (list, tuple)) else round(c, 7)


geometry = mapping(land)
geometry["coordinates"] = rounded(geometry["coordinates"])
with open(OUTPUT, "w") as f:
    json.dump(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": geometry}],
        },
        f,
        separators=(",", ":"),
    )

print(
    f"{OUTPUT}: {len(land.geoms)} polygons, "
    f"{shapely.get_num_coordinates(land)} points, "
    f"{sum(area_m2(p) for p in land.geoms) / 1e6:.2f} km²"
)
