"""Generate a reproducible road grid and enough traffic for a full episode."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

from phase1.config import ScenarioConfig, SimulationConfig
from .runtime import SumoRuntime


@dataclass(frozen=True)
class RoadTarget:
    """A reachable point on a directed lane, expressed in SUMO coordinates."""

    edge_id: str
    lane_position: float
    x: float
    y: float


def write_xml(root: ET.Element, path: Path) -> None:
    """Write generated XML with escaping and stable, readable indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def create_network(runtime: SumoRuntime, config: SimulationConfig, path: Path) -> Any:
    """Build a 5x5 signal-controlled grid spanning the original 1 km square.

    Four 250 m blocks per axis preserve the original geographic scale. One lane
    in each direction and a 50 km/h limit are ordinary urban test assumptions,
    not parameters fitted to improve either offloading method.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        runtime.netgenerate, "--grid", "--grid.x-number", "5", "--grid.y-number", "5",
        "--grid.x-length", str(config.area_width_m / 4),
        "--grid.y-length", str(config.area_height_m / 4),
        "--default.lanenumber", "1", "--default.speed", "13.89",
        "--default-junction-type", "traffic_light", "--no-turnarounds", "false",
        "--seed", str(config.seed), "--output-file", str(path),
    ], capture_output=True, text=True, check=True)
    path.with_suffix(".generation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return runtime.sumolib.net.readNet(str(path))


def project_target(network: Any, geometry: Any, x: float, y: float, excluded: str = "") -> RoadTarget:
    """Snap a desired coordinate to the nearest passenger lane, away from junctions."""

    candidates = []
    for edge in network.getEdges():
        if edge.getID() == excluded or not edge.allows("passenger"):
            continue
        lane = edge.getLane(0)
        length = lane.getLength()
        offset, _distance = geometry.polygonOffsetAndDistanceToPoint((x, y), lane.getShape())
        offset = max(20.0, min(length - 20.0, offset))
        point = geometry.positionAtShapeOffset(lane.getShape(), offset)
        distance = (point[0] - x) ** 2 + (point[1] - y) ** 2
        candidates.append((distance, edge.getID(), offset, point))
    if not candidates:
        raise RuntimeError("The road network has no suitable passenger lanes.")
    _distance, edge_id, offset, point = min(candidates)
    return RoadTarget(edge_id, offset, point[0], point[1])


def create_routes(
    network: Any, scenario: ScenarioConfig, config: SimulationConfig,
    warmup_s: float, path: Path,
) -> None:
    """Create identical seeded initial traffic and parked providers for each method.

    Cars start on distinct directed edges to avoid insertion queues. Routes are
    long enough for the whole episode, so there is no recycling or teleporting.
    Providers initially park beside the road; only SDN runs redirect them.
    """

    rng = Random(config.seed + 101)
    edges = sorted((edge for edge in network.getEdges() if edge.allows("passenger")),
                   key=lambda edge: edge.getID())
    starts = rng.sample(edges, scenario.vehicle_count + scenario.provider_count)
    root = ET.Element("routes")
    for name, color in (("car", "0,0.65,0.85"), ("provider", "0.95,0.35,0.1")):
        ET.SubElement(root, "vType", id=name, vClass="passenger", color=color,
                      accel="2.6", decel="4.5", sigma="0.5", length="5", minGap="2.5",
                      maxSpeed=str(config.vehicle_max_speed_mps), speedDev="0")
    horizon = warmup_s + config.steps * config.time_step_s
    for index, start in enumerate(starts):
        provider = index >= scenario.vehicle_count
        node_id = index - scenario.vehicle_count if provider else index
        vehicle_id = f"provider:{node_id}" if provider else f"vehicle:{node_id}"
        route = [start]
        distance = start.getLength()
        while not provider and distance < 2 * config.vehicle_max_speed_mps * horizon:
            destination = rng.choice(edges)
            extension, _cost = network.getShortestPath(route[-1], destination, vClass="passenger")
            if extension and len(extension) > 1:
                route.extend(extension[1:])
                distance += sum(edge.getLength() for edge in extension[1:])
        stop_position = start.getLength() / 2
        speed_factor = rng.uniform(config.vehicle_min_speed_mps, config.vehicle_max_speed_mps) / 13.89
        vehicle = ET.SubElement(root, "vehicle", id=vehicle_id,
                                type="provider" if provider else "car", depart="0",
                                departPos=str(stop_position - 10 if provider else 10),
                                departSpeed="0", speedFactor=str(1.0 if provider else speed_factor))
        ET.SubElement(vehicle, "route", edges=" ".join(edge.getID() for edge in route))
        if provider:
            ET.SubElement(vehicle, "stop", lane=start.getLane(0).getID(),
                          endPos=str(stop_position), duration=str(horizon + 3600), parking="true")
    write_xml(root, path)


def create_sumo_config(network_path: Path, route_path: Path, step_s: float, seed: int, path: Path) -> None:
    """Write a portable scenario file using paths relative to the scenario folder."""

    import os

    root = ET.Element("configuration")
    inputs = ET.SubElement(root, "input")
    ET.SubElement(inputs, "net-file", value=Path(os.path.relpath(network_path.resolve(), path.parent.resolve())).as_posix())
    ET.SubElement(inputs, "route-files", value=route_path.name)
    time = ET.SubElement(root, "time")
    ET.SubElement(time, "step-length", value=str(step_s))
    random = ET.SubElement(root, "random_number")
    ET.SubElement(random, "seed", value=str(seed))
    write_xml(root, path)
