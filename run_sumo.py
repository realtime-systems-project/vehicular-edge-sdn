#!/usr/bin/env python3
"""Run the isolated SUMO experiment without changing the course benchmark."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from phase1.config import SCENARIOS, Phase2Config, SimulationConfig
from sumo_experiment.runner import run_experiment
from sumo_experiment.runtime import load_runtime


def positive_int(value: str) -> int:
    """Reject zero or negative episode counts and simulation lengths."""

    number = int(value)
    if number <= 0:
        raise ValueError("Must be a positive integer.")
    return number


def main() -> None:
    """Resolve SUMO, run training and evaluation, and print the output location."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("1", "2", "all"), default="all")
    parser.add_argument("--steps", type=positive_int, default=120)
    parser.add_argument("--episodes", type=positive_int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sumo-home", type=Path, help="SUMO folder containing bin/ and tools/.")
    parser.add_argument("--output", type=Path, default=None, help="A fresh experiment folder.")
    parser.add_argument("--gui", action="store_true", help="Show evaluation episodes in SUMO GUI.")
    parser.add_argument("--gui-delay-ms", type=int, default=100)
    parser.add_argument("--warmup-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if args.warmup_seconds < 0 or args.gui_delay_ms < 0:
        parser.error("Warmup and GUI delay cannot be negative.")
    output = args.output or Path("sandbox/sumo") / datetime.now().strftime("run-%Y%m%d-%H%M%S-%f")
    scenario_ids = (1, 2) if args.scenario == "all" else (int(args.scenario),)
    try:
        runtime = load_runtime(args.sumo_home)
        print(runtime.version(), flush=True)
        summaries = run_experiment(
            [SCENARIOS[index] for index in scenario_ids],
            replace(SimulationConfig(), steps=args.steps, seed=args.seed),
            replace(Phase2Config(), training_episodes=args.episodes, evaluation_steps=args.steps),
            runtime, output.resolve(), args.warmup_seconds, args.gui, args.gui_delay_ms,
        )
    except (RuntimeError, FileExistsError) as error:
        parser.exit(1, str(error) + "\n")
    for summary in summaries:
        print(f"{summary.scenario_name} {summary.method_name}: "
              f"delay={summary.average_delay_s:.4f}s loss={summary.average_packet_loss:.4f} "
              f"missed={summary.missed_deadlines} blind={summary.blind_spots}")
    print(f"Results: {output.resolve()}")


if __name__ == "__main__":
    main()
