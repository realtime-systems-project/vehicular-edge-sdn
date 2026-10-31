# SUMO Integration

The current `main` branch couples the course simulator to real SUMO road traffic.
The original Phase 1/2 runners and their saved benchmark results remain available.
The Python package retains its historical name, `sumo_experiment`, so existing
commands and imports continue to work.

## Setup

Tested with Python 3.11 and **SUMO 1.28.0**. Install the native SUMO application
from the [official installation guide](https://sumo.dlr.de/docs/Installing/).
The Python `traci` package alone does not install the simulator executables.

On macOS, install and open [XQuartz](https://www.xquartz.org/) for GUI runs.
Headless runs do not need XQuartz. The runner recognizes the official macOS
SUMO framework automatically. Otherwise, set `SUMO_HOME` to your installation's
folder containing `bin/` and `tools/`, or pass `--sumo-home /path/to/sumo`.
On Windows, use `python` instead of `python3` in the commands below.

If `SUMO_HOME/tools` contains `traci` and `sumolib`, no Python package install is
needed. Otherwise use a virtual environment and install the matching interface:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-sumo.txt
```

On Windows, activate with `.venv\Scripts\activate` instead. Ensure `sumo` and
`netgenerate` are available under `SUMO_HOME/bin` or on `PATH`; GUI runs also
need `sumo-gui`. Rebuilding maps additionally needs `netconvert` and `polyconvert`.

## Quick Start

Run from the repository root after pulling `main`. Bundled city maps work
offline; no map download or rebuild is needed for normal simulation.

```bash
# Short headless check.
python3 run_sumo.py --map dinkelsbuhl --scenario demo --episodes 1 --steps 40

# Compact town with visible provider movement.
python3 run_sumo.py --map dinkelsbuhl --scenario demo --episodes 2 --steps 300 --gui --gui-delay-ms 200

# Original grid, both course populations.
python3 run_sumo.py --map grid --scenario all --episodes 24 --steps 120

# Larger real city district.
python3 run_sumo.py --map erlangen --scenario 2 --episodes 2 --steps 120 --gui
```

`--episodes` controls training episodes; `--steps` controls the length of each
training and evaluation episode. `--seed` defaults to 7. `--warmup-seconds`
defaults to 30, and `--gui-delay-ms` controls playback speed, not simulated time.
One simulation step is one simulated second with the current configuration.
Use `python3 run_sumo.py --help` for all options.

## Maps And Populations

| Option | Meaning |
| --- | --- |
| `--map grid` | Generated 5x5 road grid, about 1 km per side; default. |
| `--map erlangen` | Real OSM district, about 1.28 x 1.29 km. |
| `--map dinkelsbuhl` | Real compact old-town district, about 668 x 709 m. |
| `--scenario 1` | 20 cars, 3 providers, 2 fixed edge servers. |
| `--scenario 2` | 50 cars, 6 providers, 4 fixed edge servers. |
| `--scenario all` | Both course populations, separately; default. |
| `--scenario demo` | 40 cars, 12 providers, 8 edge servers; display-only population. |

The demo doubles scenario 2's infrastructure on a much smaller map. Radio
ranges are unchanged, so blind spots may disappear. Its results are not directly
comparable with the course benchmark and do not establish an RL improvement.

## Understanding The GUI

Every scenario runs **headless training, baseline GUI, then controlled GUI**
when `--gui` is enabled. Check the terminal's evaluation name to identify the
current window. Without `--gui`, both evaluations are headless too.

| Color | Meaning |
| --- | --- |
| Cyan cars | Ordinary vehicles generating tasks; follow seeded synthetic routes. |
| Orange delivery vehicles | Mobile compute providers. |
| Green markers | Fixed edge servers. |
| Yellow markers | Current road-accessible provider destinations, not coverage zones. |

**Parked providers and no yellow dots are expected in the baseline.** In the
controlled evaluation, providers drive to SDN destinations and park until
redirected. The GUI shows traffic and destinations, not animated packets or jobs.
Opening a saved `.sumocfg` alone plays traffic without the Python SDN/task loop;
use `run_sumo.py --gui` for the coupled simulation.

## How The Integration Works

`SumoEnvironment` subclasses the original `SimulationEnvironment`. Python
starts a SUMO process and communicates over local TCP through **TraCI**.
**sumolib** reads road networks and geometry.

Each simulated second, Python uses actual SUMO positions, updates SDN targets
when due, generates tasks, evaluates offloading choices, updates queues and
metrics, then advances SUMO and synchronizes positions again. Offloading still
considers local execution, a provider, a direct edge link, or an edge via a
provider. These use the original analytical network and compute model.

Every 10 simulated seconds, the controlled run requests provider destinations.
The original controller first computes `current + 0.75 * (desired - current)`.
The adapter snaps that intermediate point onto a suitable passenger lane and
uses TraCI `changeTarget` and `setStop` to request driving and parking. SUMO
handles road routing, speed, braking, and traffic rules; providers never
teleport. Unsafe junction/reinsertion updates are deferred. A new destination
can replace an old one before arrival. The 75% factor changes the destination,
not driving speed, and is retained from the original controller.

Training samples strategies and updates the existing PPO-style policy. Both
evaluations use a matched held-out seed; the controlled evaluation fixes the
best training-observed strategy, but recomputes its target positions. It does
not search for a winning strategy on the evaluation episode. Workload, weather,
and Kalman noise have separate random streams, preserving matched task inputs.

## Files And Outputs

| Source | Responsibility |
| --- | --- |
| `run_sumo.py` | CLI, runtime selection, scenario selection. |
| `runtime.py` | Find native executables and Python interfaces. |
| `city.py`, `maps/` | Map import, bundled assets, source/license metadata. |
| `network.py` | Grid generation, seeded routes, road-target projection, configs. |
| `environment.py` | TraCI lifecycle, actual positions, provider driving, task integration. |
| `runner.py` | Training, held-out evaluations, metrics and traces. |
| `gui.py` | View settings and macOS display/authentication checks. |
| `scenarios.py` | Additional compact demo population only. |
| `plot_mobility.py` | Optional Matplotlib export of actual provider paths. |

Runs create fresh timestamped folders under `sandbox/sumo/`. `--output` must
point to a new or empty folder; previous results are never overwritten.

| Output | Contents |
| --- | --- |
| `manifest.json` | Configuration, seeds, strategy, runtime and diagnostics. |
| `summary.csv`, `convergence.csv` | Evaluation summaries and training history. |
| `plots/*.svg` | Six project metric plots. |
| `network/` | Shared roads and, for city maps, polygons and provenance. |
| `<scenario>/training/episode_*/` | Training traffic configuration and SUMO logs. |
| `<scenario>/baseline/`, `controlled/` | Evaluation configs, logs and traces. |
| `metrics.csv`, `tasks.csv` | Per-step metrics and task/offloading decisions. |
| `mobility.csv`, `mobility.fcd.xml`, `trips.xml` | Actual positions and trip diagnostics. |
| `actions.csv`, `provider_targets.csv` | Controlled strategy changes and requested/road targets. |
| `sumo-start.png`, `sumo-view.png`, `sumo-end.png` | Evaluation screenshots when GUI is enabled. |

Optional trajectory export (replace the path with your actual run folder):

```bash
python3 -m pip install matplotlib
python3 -m sumo_experiment.plot_mobility sandbox/sumo/run-YOUR-TIMESTAMP
```

This writes `plots/mobility.png` for either grid or city runs. Sandbox results,
private explanatory notes, and teammate guide PDFs are not published in Git.

## Checks And Troubleshooting

```bash
python3 -m unittest discover -s tests -p 'test_sumo*.py' -v
```

Integration tests require native SUMO, even though GUI preflight tests are mocked.
Checks cover connectivity, population stability, motion, matched workloads,
held-out seeds, safe provider destinations, and XQuartz authentication recovery.

- **Cannot find SUMO / cannot import traci:** check `SUMO_HOME`, `--sumo-home`,
  and your active Python environment. Prefer interfaces bundled with your SUMO.
- **No accessible macOS display:** open XQuartz. The launcher checks display
  addresses and can recover a same-user token saved under an old hostname using
  a private temporary authority file. It never disables authentication or edits
  `~/.Xauthority`. That temporary file is removed on normal Python exit.
- **Missing `/tmp/.X11-unix`:** only if the launcher reports this exact problem,
  run `sudo install -d -o root -g wheel -m 1777 /tmp/.X11-unix` in Terminal,
  reopen XQuartz, and retry. Do not use `xhost +` to bypass authentication.
- **Slow first GUI launch:** macOS native-library startup can be slow; the GUI
  connection allows up to 120 one-second retries. Inspect the episode's
  `sumo.log` if it still fails.
- **No moving providers or yellow dots:** confirm the terminal says
  `controlled evaluation`, not `baseline evaluation` or warmup.
- **Output folder is not empty:** omit `--output` or choose a new directory.

## Limits And Map Provenance

The city geometry is real; traffic demand and fixed signal timings are
synthetic and uncalibrated. Buildings are visual only, not radio obstacles.
Packet loss, expected retransmissions, delay, and CPU queues remain analytical
Python estimates, not packet-level or real-application execution. The existing
controller is PPO-style, not full neural PPO or learned CTDE.

Provider destinations are not optimally matched by driving time. SUMO can
estimate route travel times, but we do not yet use them to optimize assignments
or penalize frequent retargeting. One held-out seed and short demo training are
exploratory, not evidence of statistical superiority. SUMO versions/platforms
can also change exact traffic behavior.

Map data: [OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright).
Each `maps/<name>/provenance.json` records the source URL, geographic bounds,
source checksum, dates, SUMO version and import commands. The compressed network
and polygon files are bundled. Preparation retains the largest mutually
reachable passenger-road component and removes unrelated OSM POIs.

To explicitly rebuild a map with native SUMO tools:

```bash
python3 -m sumo_experiment.city --map dinkelsbuhl
python3 -m sumo_experiment.city --map erlangen
```

The source is cached under `sandbox/sumo/map-source/<name>/source.osm.xml`.
Rebuilding uses that cached snapshot; move it aside first if you deliberately
want to download newer OSM data. Rebuilding changes bundled assets, so review
them before committing. Normal runs never download maps automatically.
