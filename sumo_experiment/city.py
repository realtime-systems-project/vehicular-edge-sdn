"""Prepare an attributed OpenStreetMap district for repeatable city experiments.

Run with python -m sumo_experiment.city. Downloads are explicit preparation,
never a side effect of running a simulation. Traffic demand remains synthetic.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .runtime import load_runtime


CITY_DIRECTORY = Path(__file__).resolve().parent / "maps" / "erlangen"
BBOX = "11.000,49.591,11.014,49.601"
SOURCE = "https://www.openstreetmap.org/api/0.6/map?bbox=" + BBOX


def connected_edges(network: object) -> list:
    """Find the largest mutually reachable passenger-road component.

    Forward/reverse reachability intersection gives the component containing
    each remaining seed. This avoids adding a graph-library dependency.
    """

    remaining = {edge for edge in network.getEdges() if edge.allows("passenger")}
    largest = set()
    while remaining:
        seed = min(remaining, key=lambda edge: edge.getID())
        component = (network.getReachable(seed, "passenger") &
                     network.getReachable(seed, "passenger", useIncoming=True))
        remaining.difference_update(component)
        if len(component) > len(largest):
            largest = component
    return sorted(largest, key=lambda edge: edge.getID())


def prepare_city() -> None:
    """Download, import, prune disconnected streets, and preserve map provenance."""

    runtime = load_runtime()
    home = Path(runtime.sumolib.__file__).resolve().parents[2]
    output = CITY_DIRECTORY
    output.mkdir(parents=True, exist_ok=True)
    cache = Path("sandbox/sumo/map-source/erlangen")
    cache.mkdir(parents=True, exist_ok=True)
    source = cache / "source.osm.xml"
    if not source.exists():
        request = urllib.request.Request(SOURCE, headers={"User-Agent": "RealtimeCourseSUMO/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            source.write_bytes(response.read())
    binary = Path(runtime.netgenerate).with_name("netconvert")
    raw = cache / "raw.net.xml"
    commands = [[str(binary), "--osm-files", str(source),
                 "--keep-edges.by-vclass", "passenger", "--keep-edges.in-geo-boundary", BBOX,
                 "--geometry.remove", "--ramps.guess", "--junctions.join",
                 "--tls.guess-signals", "--tls.discard-simple", "--tls.default-type", "actuated",
                 "--remove-edges.isolated", "--output.street-names", "true",
                 "--output-file", str(raw)]]
    result = subprocess.run(commands[0], capture_output=True, text=True, check=True)
    (cache / "import.log").write_text(result.stdout + result.stderr)
    network = runtime.sumolib.net.readNet(str(raw))
    keep = cache / "connected-edges.txt"
    keep.write_text("\n".join(edge.getID() for edge in connected_edges(network)))
    net_path = output / "city.net.xml.gz"
    commands.append([str(binary), "--sumo-net-file", str(raw),
                     "--keep-edges.input-file", str(keep), "--offset.disable-normalization", "false",
                     "--tls.rebuild", "true", "--tls.default-type", "static",
                     "--output-file", str(net_path)])
    result = subprocess.run(commands[-1], capture_output=True, text=True, check=True)
    (cache / "connectivity.log").write_text(result.stdout + result.stderr)
    polyconvert = binary.with_name("polyconvert")
    commands.append([str(polyconvert), "--net-file", str(net_path), "--osm-files", str(source),
                     "--type-file", str(home / "data/typemap/osmPolyconvert.typ.xml"),
                     "--prune.in-net", "--output-file", str(output / "city.poly.xml.gz")])
    result = subprocess.run(commands[-1], capture_output=True, text=True, check=True)
    (cache / "polygons.log").write_text(result.stdout + result.stderr)
    # OSM shop/tree/address POIs overwhelm the project vehicle/server markers.
    polygons = output / "city.poly.xml.gz"
    with gzip.open(polygons, "rb") as handle:
        shapes = ET.parse(handle)
    for poi in list(shapes.getroot().findall("poi")):
        shapes.getroot().remove(poi)
    with gzip.open(polygons, "wb") as handle:
        shapes.write(handle, encoding="utf-8", xml_declaration=True)
    metadata = {"city": "Central Erlangen, Germany", "source_url": SOURCE,
                "bbox_wgs84": BBOX,
                "retrieved_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                "prepared_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "attribution": "Map data copyright OpenStreetMap contributors",
                "license": "https://www.openstreetmap.org/copyright",
                "sumo_version": runtime.version(), "commands": commands,
                "traffic": "Seeded synthetic project vehicles, not measured city demand",
                "signals": "OSM signals plus inferred groups; rebuilt fixed timings, uncalibrated"}
    metadata["visualization"] = "Building/land-use polygons retained; unrelated OSM POIs removed"
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Prepared city map: {net_path}")


if __name__ == "__main__":
    prepare_city()
