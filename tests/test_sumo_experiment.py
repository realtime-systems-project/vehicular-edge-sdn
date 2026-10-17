"""Integration checks against real SUMO, run with unittest discovery."""

from __future__ import annotations

import csv
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from phase1.config import SCENARIOS, Phase2Config, SimulationConfig
from phase1.models import Position
from phase2.kalman import LinkQualityEstimator
from sumo_experiment.environment import SumoEnvironment
from sumo_experiment.network import create_network
from sumo_experiment.runner import run_experiment
from sumo_experiment.runtime import load_runtime


class SumoIntegrationTests(unittest.TestCase):
    """Check real mobility, matched randomness, population, and evaluation isolation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build one test network using a real local SUMO installation."""

        cls.runtime = load_runtime()
        cls.temporary = tempfile.TemporaryDirectory(prefix="sumo-tests-")
        cls.directory = Path(cls.temporary.name)
        cls.config = replace(SimulationConfig(), steps=25)
        cls.phase2 = replace(Phase2Config(), training_episodes=1, evaluation_steps=25)
        cls.network_path = cls.directory / "grid.net.xml"
        cls.network = create_network(cls.runtime, cls.config, cls.network_path)

    @classmethod
    def tearDownClass(cls) -> None:
        """Remove test artifacts after all SUMO processes have closed."""

        cls.temporary.cleanup()

    def environment(self, name: str) -> SumoEnvironment:
        """Create a fresh episode with the same traffic and workload seed."""

        return SumoEnvironment(SCENARIOS[1], self.config, self.runtime,
                               self.network, self.network_path, self.directory / name)

    def test_tasks_and_weather_ignore_measurement_rng(self) -> None:
        """Different Kalman calls must not change the physical workload or weather."""

        observed = []
        for noise in (False, True):
            with self.environment(f"randomness-{noise}") as environment:
                trace = []
                estimator = LinkQualityEstimator(self.phase2)
                for step in range(25):
                    if noise:
                        for _ in range(30):
                            estimator.estimate("vehicle:0", "provider:0", 0.2, environment.rng)
                    trace.append(([asdict(task) for task in environment.generate_tasks()], environment.weather))
                    environment.advance()
                observed.append(trace)
        self.assertEqual(observed[0], observed[1])

    def test_provider_drives_instead_of_teleporting(self) -> None:
        """An SDN request leaves current coordinates intact and motion is speed bounded."""

        with self.environment("provider-motion") as environment:
            before = [Position(node.position.x, node.position.y) for node in environment.providers]
            environment.set_provider_positions([Position(950, 950), Position(50, 950), Position(950, 50)])
            self.assertEqual(before, [node.position for node in environment.providers])
            travelled = 0.0
            for _ in range(25):
                previous = [node.position for node in environment.providers]
                environment.advance()
                for node, old in zip(environment.providers, previous):
                    distance = node.position.distance_to(old)
                    self.assertLessEqual(distance, self.config.vehicle_max_speed_mps * self.config.time_step_s + 1)
                    travelled += distance
                self.assertEqual(len(environment.active_ids | environment.reinserting), 23)
            self.assertGreater(travelled, 10)
            self.assertGreater(environment.reroutes, 0)

    def test_comparison_uses_identical_tasks_and_unseen_seed(self) -> None:
        """Both evaluations use the same task attributes and no evaluation strategy sweep."""

        import json

        output = self.directory / "comparison"
        summaries = run_experiment([SCENARIOS[1]], self.config, self.phase2, self.runtime, output)
        self.assertEqual(len(summaries), 2)
        manifest = json.loads((output / "manifest.json").read_text())
        scenario = manifest["scenarios"][0]
        self.assertNotIn(scenario["evaluation_seed"], scenario["training_seeds"])
        workload = []
        task_fields = ("task_id", "vehicle_id", "created_at_step", "data_size_mbits",
                       "compute_cycles_g", "deadline_s")
        for method in ("baseline", "controlled"):
            with (output / "scenario_1" / method / "tasks.csv").open() as handle:
                workload.append([tuple(row[field] for field in task_fields) for row in csv.DictReader(handle)])
        self.assertTrue(workload[0])
        self.assertEqual(workload[0], workload[1])
        with (output / "scenario_1" / "controlled" / "actions.csv").open() as handle:
            strategies = {row["strategy"] for row in csv.DictReader(handle)}
        self.assertEqual(strategies, {scenario["selected_strategy"]})
        self.assertEqual(len(list((output / "plots").glob("*.svg"))), 6)
        with self.assertRaises(FileExistsError):
            run_experiment([SCENARIOS[1]], self.config, self.phase2, self.runtime, output)


if __name__ == "__main__":
    unittest.main()
