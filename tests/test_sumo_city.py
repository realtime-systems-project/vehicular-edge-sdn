"""Validate the bundled real city and its coupled SUMO traffic behavior."""

import gzip
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from phase1.config import SCENARIOS, SimulationConfig
from phase1.models import Position
from sumo_experiment.city import CITY_DIRECTORY, connected_edges
from sumo_experiment.environment import SumoEnvironment
from sumo_experiment.network import project_target
from sumo_experiment.runtime import load_runtime


class CityTests(unittest.TestCase):
    """Exercise actual imported roads, not a mock network."""

    def test_connected_map_and_driving(self) -> None:
        """Every road is reachable; traffic moves without missing nodes or teleports."""

        runtime = load_runtime()
        path = CITY_DIRECTORY / "city.net.xml.gz"
        network = runtime.sumolib.net.readNet(str(path))
        self.assertEqual(len(connected_edges(network)), len(network.getEdges()))
        self.assertGreater(len(network.getEdges()), 100)
        xmin, ymin, xmax, ymax = network.getBoundary()
        self.assertEqual((xmin, ymin), (0, 0))
        self.assertTrue(900 < xmax < 1600 and 900 < ymax < 1600)
        with gzip.open(CITY_DIRECTORY / "city.poly.xml.gz") as handle:
            shapes = ET.parse(handle).getroot()
            self.assertGreater(len(shapes), 100)
            self.assertFalse(shapes.findall("poi"))
        metadata = json.loads((CITY_DIRECTORY / "provenance.json").read_text())
        self.assertIn("openstreetmap", metadata["license"])
        config = replace(SimulationConfig(), steps=120, area_width_m=xmax, area_height_m=ymax)
        with tempfile.TemporaryDirectory() as directory:
            with SumoEnvironment(SCENARIOS[2], config, runtime, network, path,
                                 Path(directory)) as environment:
                before = [node.position for node in environment.vehicles]
                environment.set_provider_positions([Position(xmax / 2, ymax / 2)] * 6)
                for _ in range(120):
                    environment.advance()
                self.assertGreater(sum(node.position.distance_to(old)
                                       for node, old in zip(environment.vehicles, before)), 100)
                self.assertEqual(len(environment.active_ids | environment.reinserting), 56)
                for target in environment.targets.values():
                    lane = network.getEdge(target.edge_id).getLane(target.lane_index)
                    self.assertTrue(lane.allows("passenger"))
                    self.assertTrue(20 <= target.lane_position <= lane.getLength() - 20)
                target = project_target(network, runtime.sumolib.geomhelper, 0, 0)
                self.assertGreaterEqual(target.lane_position, 20)
            vehicles = ET.parse(Path(directory) / "traffic.rou.xml").findall("vehicle")
            self.assertTrue(all(float(vehicle.get("speedFactor")) <= 1 for vehicle in vehicles))


if __name__ == "__main__":
    unittest.main()
