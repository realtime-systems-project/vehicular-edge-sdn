"""Validate the bundled real city and its coupled SUMO traffic behavior."""

import gzip
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from phase1.config import SCENARIOS, SimulationConfig, Phase2Config
from phase1.models import Position
from sumo_experiment.city import CITY_DIRECTORY, connected_edges, city_directory
from sumo_experiment.environment import SumoEnvironment
from sumo_experiment.network import project_target
from sumo_experiment.runtime import load_runtime
from sumo_experiment.runner import run_experiment
from sumo_experiment.scenarios import COMPACT_DEMO


class CityTests(unittest.TestCase):
    """Exercise actual imported roads, not a mock network."""

    def test_compact_town_and_extra_infrastructure(self) -> None:
        """The demo uses a smaller connected map and preserves course population counts."""

        runtime = load_runtime()
        path = city_directory("dinkelsbuhl") / "city.net.xml.gz"
        network = runtime.sumolib.net.readNet(str(path))
        self.assertEqual(len(connected_edges(network)), len(network.getEdges()))
        xmin, ymin, width, height = network.getBoundary()
        self.assertEqual((xmin, ymin), (0, 0))
        self.assertTrue(400 < width < 800 and 400 < height < 800)
        self.assertEqual((COMPACT_DEMO.vehicle_count, COMPACT_DEMO.provider_count,
                          COMPACT_DEMO.edge_count), (40, 12, 8))
        self.assertEqual((SCENARIOS[2].provider_count, SCENARIOS[2].edge_count), (6, 4))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "comparison"
            run_experiment([COMPACT_DEMO], replace(SimulationConfig(), steps=40),
                           replace(Phase2Config(), training_episodes=1), runtime, output,
                           map_name="dinkelsbuhl")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["network"], "dinkelsbuhl")
            self.assertAlmostEqual(manifest["simulation"]["area_width_m"], width)
            self.assertTrue((output / "network" / "provenance.json").exists())
            for method in ("baseline", "controlled"):
                episode = output / "compact_demo" / method
                vehicles = ET.parse(episode / "traffic.rou.xml").findall("vehicle")
                self.assertEqual(sum(v.get("type") == "provider" for v in vehicles), 12)
                self.assertEqual(len(vehicles), 52)
                diagnostics = manifest["scenarios"][0]["evaluation_diagnostics"][method]
                self.assertEqual(diagnostics["active_vehicles"], 52)
                self.assertEqual(diagnostics["collisions"], 0)
                self.assertEqual(diagnostics["teleports"], 0)

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
