#!/usr/bin/env python3
"""Run the full Phase 2 SDN/RL simulation and generate comparison plots."""

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import List

from phase1.config import SCENARIOS, Phase2Config, SimulationConfig
from phase2.runner import run_phase2_for_scenarios


def parse_args() -> object:
    """Read command-line options for Phase 2 training and evaluation."""

    parser = ArgumentParser(description="Run Phase 2 SDN/RL simulations.")
    parser.add_argument(
        "--scenario",
        choices=["1", "2", "all"],
        default="all",
        help="Which project scenario to run.",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=24,
        help="Training episodes for the SDN placement controller.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=120,
        help="Evaluation steps per scenario.",
    )
    parser.add_argument("--seed", type=int, default=7, help="Base random seed.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/phase2"),
        help="Directory for generated Phase 2 CSV and SVG files.",
    )
    return parser.parse_args()


def main() -> None:
    """Run selected scenarios, write outputs, and print a compact comparison."""

    args = parse_args()
    scenario_ids: List[int] = [1, 2] if args.scenario == "all" else [int(args.scenario)]
    sim_config = replace(SimulationConfig(), seed=args.seed)
    phase2_config = replace(
        Phase2Config(),
        training_episodes=args.episodes,
        evaluation_steps=args.steps,
    )
    summaries = run_phase2_for_scenarios(
        scenarios=[SCENARIOS[scenario_id] for scenario_id in scenario_ids],
        sim_config=sim_config,
        phase2_config=phase2_config,
        output_dir=args.output,
    )
    print_summary(summaries, args.output)


def print_summary(summaries: list, output_dir: Path) -> None:
    """Print the baseline-vs-Phase-2 comparison table."""

    print(f"Phase 2 results written to: {output_dir}")
    print()
    print("scenario     method            avg_loss  avg_delay_s  missed  blind_spots")
    for summary in summaries:
        print(
            f"{summary.scenario_name:<12}"
            f"{summary.method_name:<18}"
            f"{summary.average_packet_loss:>8.4f}  "
            f"{summary.average_delay_s:>11.4f}  "
            f"{summary.missed_deadlines:>6}  "
            f"{summary.blind_spots:>11}"
        )


if __name__ == "__main__":
    main()

