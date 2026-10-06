"""Check the government sources for updates and rebuild what changed.

    python update.py

Run daily by .github/workflows/update.yml. It compares the iB5000 sheet index
with sheets.json, rebuilds the land if any sheet was revised, and always
rebuilds the boundary (one small download). A rebuilt file that differs from
the committed one by less than MIN_CHANGE_M2 is put back as it was, so float
noise never makes a release. Then it says what to do:

    release   the land or the boundary changed: commit and publish a release
    commit    only sheets.json changed: commit, no release

Under GitHub Actions these go to $GITHUB_OUTPUT, with the commit message, and
the release notes go to $RUNNER_TEMP/notes.md. Locally they are printed.

A change of more than MAX_CHANGE_KM2 stops the run for a human look, unless
ALLOW_LARGE_CHANGE=1 is set.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import shapely
from shapely.ops import transform

import build

MIN_CHANGE_M2 = 1.0
MAX_CHANGE_KM2 = 5.0

LAND_FILES = (build.OUTPUT, build.OUTPUT_LIGHT, build.OUTPUT_MASK)
FILES = (*LAND_FILES, build.OUTPUT_BOUNDARY)


def grid(geometry):
    return transform(build.TO_GRID, geometry)


def iso(date):
    return f"{date[:4]}-{date[4:6]}-{date[6:]}"


def latest_tag():
    tags = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"], capture_output=True, text=True, check=True
    ).stdout.split()
    return tags[0] if tags else None


def main():
    with open(build.MANIFEST) as f:
        before = json.load(f)
    index = build.fetch_index()
    after = {s: index[s]["REVISIONDATE"] for s in sorted(index)}
    revised = sorted(s for s in before.keys() | after.keys() if before.get(s) != after.get(s))

    old = {path: Path(path).read_bytes() for path in FILES}
    if revised:
        print(f"{len(revised)} sheets revised: {', '.join(revised)}", file=sys.stderr)
        build.build_land(index)
    else:
        print("no sheets revised", file=sys.stderr)
    build.build_boundary()

    # Compare in the grid, so areas are in square metres.
    changes = {}
    for path, files in ((build.OUTPUT, LAND_FILES), (build.OUTPUT_BOUNDARY, (build.OUTPUT_BOUNDARY,))):
        was = grid(shapely.from_geojson(old[path]).geoms[0])
        now = grid(build.read_geometry(path))
        diff = was.symmetric_difference(now)
        if diff.area < MIN_CHANGE_M2:
            for p in files:
                Path(p).write_bytes(old[p])
            continue
        changes[path] = (was.area, now.area, diff)

    large = [f"{p} changed by {d.area / 1e6:.2f} km²" for p, (_, _, d) in changes.items()
             if d.area / 1e6 > MAX_CHANGE_KM2]
    if large and os.environ.get("ALLOW_LARGE_CHANGE") != "1":
        for path in FILES:
            Path(path).write_bytes(old[path])
        sys.exit(
            "; ".join(large) + f", more than {MAX_CHANGE_KM2} km². Check the build by hand, "
            "then rerun the workflow with allow_large_change."
        )

    build.update_docs()

    as_of = iso(max(after.values()))
    release = bool(changes)
    if release:
        parts = []
        if build.OUTPUT in changes:
            parts.append(f"the iB5000 map as of {as_of}")
        if build.OUTPUT_BOUNDARY in changes:
            parts.append("the district boundaries")
        message = "Update to " + " and ".join(parts)
    else:
        message = f"Record iB5000 sheet revisions to {as_of}"
    commit = release or bool(revised)

    notes = release_notes(changes, index, as_of) if release else ""
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a") as f:
            f.write(f"release={str(release).lower()}\ncommit={str(commit).lower()}\nmessage={message}\n")
        Path(os.environ["RUNNER_TEMP"], "notes.md").write_text(notes)
    elif not commit:
        print("nothing to do")
    else:
        print(f"release={release} commit={commit}\nmessage: {message}")
        if notes:
            print(f"\n{notes}")


def release_notes(changes, index, as_of):
    previous = latest_tag()
    lines = []
    if build.OUTPUT in changes:
        was, now, diff = changes[build.OUTPUT]
        sheets = sorted(
            s for s in index
            if grid(shapely.geometry.shape(index[s]["geometry"])).intersection(diff).area >= MIN_CHANGE_M2
        )
        lines.append(
            f"Rebuilt from the Lands Department's iB5000 map as revised up to {as_of}. "
            f"The land changed by {diff.area / 1e6:,.4f} km² "
            f"({was / 1e6:,.2f} → {now / 1e6:,.2f} km²)"
            + (f", in map sheets {', '.join(sheets)}." if sheets else ".")
        )
    else:
        lines.append(f"The land files and the sea mask are the same as {previous}.")
    if build.OUTPUT_BOUNDARY in changes:
        was, now, diff = changes[build.OUTPUT_BOUNDARY]
        lines.append(
            f"The boundary changed by {diff.area / 1e6:,.4f} km² ({was / 1e6:,.2f} → {now / 1e6:,.2f} km²), "
            "following an update to the Home Affairs Department's district boundaries."
        )
    else:
        lines.append(f"The boundary is the same as {previous}.")
    return "\n\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
