"""Train and compare the existing methods on seeded SUMO traffic episodes."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from random import Random
from typing import Sequence

from phase1.config import Phase2Config, ScenarioConfig, SimulationConfig
from phase1.models import SimulationSummary
from phase1.offloading import TaskOffloader
from phase1.simulation import write_step_metrics_csv, write_summary_csv
from phase2.kalman import LinkQualityEstimator
from phase2.plotting import write_phase2_plots
from phase2.runner import _build_summary, _reward, _summarize_controlled_step, write_convergence_csv
from phase2.sdn_controller import SDNPlacementController
from .environment import SumoEnvironment
from .network import create_network
from .runtime import SumoRuntime


def write_rows(path: Path, rows: Sequence[dict]) -> None:
    """Write a nonempty diagnostic table using its first row's named columns."""

    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_episode(
    scenario: ScenarioConfig, config: SimulationConfig, phase2: Phase2Config,
    runtime: SumoRuntime, network: object, network_path: Path, directory: Path,
    controller: SDNPlacementController | None = None,
    training_rng: Random | None = None, warmup_s: float = 30.0,
    record: bool = False, gui: bool = False, gui_delay_ms: int = 0,
) -> tuple[SimulationSummary, list, dict]:
    """Run a baseline, sampled training policy, or fixed training-selected strategy.

    Only the SUMO environment differs from the course project. The original
    offloader, estimator, policy update, reward, and metric helpers are reused.
    Private metric helpers are deliberately reused here to avoid a second set
    of subtly different metric definitions in this isolated experiment.
    """

    estimator = LinkQualityEstimator(phase2) if controller else None
    offloader = TaskOffloader(config, loss_estimator=estimator.estimate if estimator else None)
    metrics, placements, mobility, tasks_trace, action_trace = [], [], [], [], []
    method = "sdn_ppo_kalman" if controller else "baseline_random"
    with SumoEnvironment(scenario, config, runtime, network, network_path, directory,
                         warmup_s, gui, record, gui_delay_ms) as environment:
        for _ in range(config.steps):
            if controller and environment.step_index % phase2.sdn_update_interval_steps == 0:
                if training_rng is not None:
                    action = controller.choose_action(environment, estimator.average_estimate(), training_rng)
                    placements.append(action)
                    positions, action_name = action.positions, action.action_name
                else:
                    action_name = controller.best_action_name()
                    positions = controller.force_action(action_name, environment, estimator.average_estimate())
                environment.set_provider_positions(positions)
                action_trace.append({"step": environment.step_index, "strategy": action_name})
            tasks = environment.generate_tasks()
            decisions = [offloader.decide(task, environment) for task in tasks]
            metrics.append(_summarize_controlled_step(environment, decisions))
            if record:
                mobility.extend(environment.mobility_rows())
                if gui and environment.step_index == config.steps // 2:
                    environment.connection.gui.screenshot("View #0", str(directory / "sumo-view.png"))
                if gui and environment.step_index in (0, config.steps - 1):
                    name = "sumo-start.png" if environment.step_index == 0 else "sumo-end.png"
                    environment.connection.gui.screenshot("View #0", str(directory / name))
                for decision in decisions:
                    row = asdict(decision.task)
                    row.update(destination=decision.candidate.destination_type,
                               route=decision.candidate.route_name,
                               model_delay_s=decision.candidate.total_delay_s,
                               model_loss=decision.candidate.packet_loss_probability,
                               missed_deadline=decision.candidate.missed_deadline)
                    tasks_trace.append(row)
            environment.advance()
        if record:
            mobility.extend(environment.mobility_rows())
            write_rows(directory / "mobility.csv", mobility)
            write_rows(directory / "tasks.csv", tasks_trace)
            write_rows(directory / "provider_targets.csv", environment.target_events)
            write_rows(directory / "actions.csv", action_trace)
        summary = _build_summary(scenario, config, method, metrics, environment)
        diagnostics = {"reroutes": environment.reroutes,
                       "junction_deferrals": environment.junction_deferrals,
                       "reinsertion_deferrals": environment.reinsertion_deferrals,
                       "waiting_providers": len(environment.reinserting - environment.active_ids),
                       "collisions": 0, "teleports": 0,
                       "sumo_time_s": environment.connection.simulation.getTime(),
                       "active_vehicles": len(environment.connection.vehicle.getIDList())}
    return summary, placements, diagnostics


def run_experiment(
    scenarios: Sequence[ScenarioConfig], config: SimulationConfig, phase2: Phase2Config,
    runtime: SumoRuntime, output: Path, warmup_s: float = 30.0,
    gui: bool = False, gui_delay_ms: int = 0,
    map_name: str = "grid",
) -> list[SimulationSummary]:
    """Train per scenario, then evaluate both methods on an unused matched seed.

    A fresh output folder prevents overwriting the original benchmark or an
    earlier experiment. Evaluation never tries strategies on the test episode
    to select the winner, unlike the historical Phase 2 runner.
    """

    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output folder is not empty; choose a fresh --output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if map_name == "erlangen":
        from .city import CITY_DIRECTORY

        if not (CITY_DIRECTORY / "city.net.xml.gz").exists():
            raise RuntimeError("Prepare the city first: python3 -m sumo_experiment.city")
        shutil.copytree(CITY_DIRECTORY, output / "network")
        network_path = (output / "network" / "city.net.xml.gz").resolve()
        network = runtime.sumolib.net.readNet(str(network_path))
        xmin, ymin, xmax, ymax = network.getBoundary()
        if abs(xmin) > 1 or abs(ymin) > 1:
            raise RuntimeError("City network must use a normalized local coordinate origin.")
        config = replace(config, area_width_m=xmax, area_height_m=ymax)
    elif map_name == "grid":
        network_path = (output / "network" / "grid.net.xml").resolve()
        network = create_network(runtime, config, network_path)
    else:
        raise ValueError(f"Unknown map: {map_name}")
    summaries, convergence, scenario_info = [], [], []
    for scenario in scenarios:
        print(f"{scenario.name}: training {phase2.training_episodes} SUMO episodes", flush=True)
        controller = SDNPlacementController(config, phase2)
        training_rng = Random(config.seed + 1000 + scenario.vehicle_count)
        controlled_config = replace(config, loss_weight_s=phase2.phase2_loss_weight_s,
                                    deadline_weight_s=phase2.phase2_deadline_weight_s)
        training_seeds = []
        for episode in range(phase2.training_episodes):
            seed = config.seed + scenario.vehicle_count + 17 * episode
            training_seeds.append(seed)
            summary, placements, _diagnostics = run_episode(
                scenario, replace(controlled_config, seed=seed), phase2, runtime,
                network, network_path, output / scenario.name / "training" / f"episode_{episode + 1:02d}",
                controller, training_rng, warmup_s,
            )
            reward = _reward(summary, phase2)
            advantage = controller.update(placements, reward)
            convergence.append({"scenario": scenario.name, "episode": episode + 1,
                                "reward": reward, "advantage": advantage,
                                "avg_packet_loss": summary.average_packet_loss,
                                "avg_delay_s": summary.average_delay_s,
                                "best_action": controller.best_action_name()})
            print(f"  episode {episode + 1}: reward={reward:.4f}", flush=True)
        test_seed = config.seed + 100000 + scenario.vehicle_count
        if test_seed in training_seeds:
            raise ValueError("Evaluation seed overlaps training; choose fewer episodes.")
        evaluations = {}
        for name, simulation, policy in (("baseline", config, None),
                                          ("controlled", controlled_config, controller)):
            print(f"{scenario.name}: {name} evaluation, seed {test_seed}", flush=True)
            directory = output / scenario.name / name
            summary, _placements, diagnostics = run_episode(
                scenario, replace(simulation, seed=test_seed), phase2, runtime, network,
                network_path, directory, policy, warmup_s=warmup_s,
                record=True, gui=gui, gui_delay_ms=gui_delay_ms,
            )
            summaries.append(summary)
            evaluations[name] = diagnostics
            write_step_metrics_csv(summary, directory / "metrics.csv")
        scenario_info.append({"scenario": asdict(scenario), "training_seeds": training_seeds,
                              "evaluation_seed": test_seed,
                              "selected_strategy": controller.best_action_name(),
                              "policy_probabilities": controller._policy(),
                              "evaluation_diagnostics": evaluations})
    write_summary_csv(summaries, output / "summary.csv")
    write_convergence_csv(convergence, output / "convergence.csv")
    write_phase2_plots(summaries, convergence, output / "plots")
    manifest = {"sumo_version": runtime.version(), "simulation": asdict(config),
                "phase2": asdict(phase2), "warmup_s": warmup_s,
                "network": map_name,
                "scenarios": scenario_info,
                "limitations": ["Wireless loss, retransmission delay, and compute queues are analytical Python estimates.",
                                "The existing controller is PPO-style, not full neural PPO or learned CTDE.",
                                "Weather affects the network loss model, not SUMO driving physics.",
                                "One held-out evaluation seed per scenario is exploratory, not statistical evidence."]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return summaries
