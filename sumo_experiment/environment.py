"""Run real SUMO traffic while reusing the project's compute/network model."""

from __future__ import annotations

from math import ceil, pi
from pathlib import Path
from random import Random
import time
from typing import Sequence
from uuid import uuid4

from phase1.config import ScenarioConfig, SimulationConfig
from phase1.environment import SimulationEnvironment
from phase1.models import Position
from .network import RoadTarget, create_routes, create_sumo_config, project_target
from .runtime import SumoRuntime
from .gui import write_view_settings


class SumoEnvironment(SimulationEnvironment):
    """Replace mobility and provider placement with a private TraCI connection.

    Each episode owns its SUMO process. Workload, weather, and measurement noise
    have separate random streams, so Kalman calls cannot change generated tasks.
    Packet loss and processing queues remain the original analytical model.
    """

    def __init__(
        self, scenario: ScenarioConfig, config: SimulationConfig,
        runtime: SumoRuntime, network: object, network_path: Path,
        directory: Path, warmup_s: float = 30.0, gui: bool = False,
        record: bool = False, gui_delay_ms: int = 0,
    ):
        """Start traffic, warm it up, then synchronize the Python node positions."""

        super().__init__(scenario, config)
        directory = directory.resolve()
        network_path = network_path.resolve()
        self.runtime = runtime
        self.network = network
        self.directory = directory
        self.task_rng = Random(config.seed + 2001)
        self.weather_rng = Random(config.seed + 3001)
        self.rng = Random(config.seed + 4001)
        self.targets: dict[int, RoadTarget] = {}
        self.pending_targets: dict[int, Position] = {}
        self.target_events: list[dict] = []
        self.target_pois: set[int] = set()
        self.reinserting: set[str] = set()
        self.active_ids: set[str] = set()
        self.reroutes = 0
        self.junction_deferrals = 0
        self.reinsertion_deferrals = 0
        self.connection = None
        self.gui_delay_s = gui_delay_ms / 1000.0 if gui else 0.0
        self.label = "sumo-" + uuid4().hex
        directory.mkdir(parents=True, exist_ok=True)
        route_path = directory / "traffic.rou.xml"
        config_path = directory / "simulation.sumocfg"
        create_routes(network, scenario, config, warmup_s, route_path)
        create_sumo_config(network_path, route_path, config.time_step_s, config.seed, config_path)
        binary = runtime.gui if gui else runtime.sumo
        if not binary:
            raise RuntimeError("sumo-gui is unavailable; run without --gui.")
        command = [binary, "-c", str(config_path), "--no-step-log", "true",
                   "--duration-log.disable", "true", "--time-to-teleport", "-1",
                   "--collision.action", "warn", "--log", str(directory / "sumo.log")]
        if record:
            command += ["--fcd-output", str(directory / "mobility.fcd.xml"),
                        "--tripinfo-output", str(directory / "trips.xml"),
                        "--tripinfo-output.write-unfinished", "true"]
        if gui:
            view_path = directory / "view.xml"
            write_view_settings(view_path)
            command += ["--start", "--quit-on-end", "--delay", str(gui_delay_ms),
                        "--window-size", "1280,900", "--window-pos", "50,50",
                        "--gui-settings-file", str(view_path)]
        try:
            runtime.traci.start(command, label=self.label, doSwitch=False, stdout=None,
                                numRetries=30 if gui else 3)
            self.connection = runtime.traci.getConnection(self.label)
            if gui:
                self.connection.gui.setSchema("View #0", "Course traffic")
                xmin, ymin, xmax, ymax = network.getBoundary()
                self.connection.gui.setBoundary("View #0", xmin - 30, ymin - 30, xmax + 30, ymax + 30)
            for _ in range(max(1, ceil(warmup_s / config.time_step_s))):
                self._traffic_step()
            self._sync_positions()
            for server in self.edge_servers:
                self.connection.poi.add(f"edge:{server.node_id}", server.position.x,
                                        server.position.y, (30, 180, 70, 255), poiType="edge-server",
                                        width=15, height=15)
        except runtime.traci.exceptions.FatalTraCIError as error:
            self.close()
            hint = " Check that XQuartz has a working display." if gui else ""
            raise RuntimeError(f"SUMO could not start; inspect {directory / 'sumo.log'}.{hint}") from error
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> "SumoEnvironment":
        """Expose the running environment to an episode context."""

        return self

    def __exit__(self, *_exc: object) -> None:
        """Always shut down SUMO, including when an offloading decision fails."""

        self.close()

    def close(self) -> None:
        """Close this episode's connection and wait for SUMO output to flush."""

        if self.connection is not None:
            connection, self.connection = self.connection, None
            connection.close()

    def generate_tasks(self) -> list:
        """Reuse the exact task generator with a stream isolated from Kalman noise."""

        noise_rng, self.rng = self.rng, self.task_rng
        try:
            return super().generate_tasks()
        finally:
            self.rng = noise_rng

    def _update_weather(self) -> None:
        """Keep the original weather model but isolate its random stream."""

        noise_rng, self.rng = self.rng, self.weather_rng
        try:
            super()._update_weather()
        finally:
            self.rng = noise_rng

    def advance(self) -> None:
        """Advance traffic once, read actual positions, and decay compute queues."""

        self._traffic_step()
        self.step_index += 1
        self._sync_positions()
        self._update_weather()
        for nodes in (self.vehicles, self.providers, self.edge_servers):
            self._decay_queues(nodes)
        for provider_id, position in list(self.pending_targets.items()):
            self._redirect_provider(provider_id, position)

    def set_provider_positions(self, positions: Sequence[Position]) -> None:
        """Convert SDN coordinates to drive-and-park destinations, never teleport."""

        if len(positions) != len(self.providers):
            raise ValueError("The controller must supply one target per provider.")
        for provider, position in zip(self.providers, positions):
            self.pending_targets[provider.node_id] = position
            self._redirect_provider(provider.node_id, position)

    def _redirect_provider(self, provider_id: int, position: Position) -> None:
        """Safely replace a provider's route and parking stop outside junctions.

        SUMO cannot change routes while a vehicle is inside a junction. Such
        requests are deferred until the next traffic step, retaining only the
        newest request. Stops behind a moving vehicle are mapped to another road.
        """

        vehicles = self.connection.vehicle
        vehicle_id = f"provider:{provider_id}"
        if vehicle_id in self.reinserting:
            self.reinsertion_deferrals += 1
            return
        road_id = vehicles.getRoadID(vehicle_id)
        if road_id.startswith(":"):
            self.junction_deferrals += 1
            return
        target = project_target(self.network, self.runtime.sumolib.geomhelper,
                                position.x, position.y)
        old = self.targets.get(provider_id)
        if old and old.edge_id == target.edge_id and abs(old.lane_position - target.lane_position) < 5:
            self.pending_targets.pop(provider_id, None)
            return
        speed = vehicles.getSpeed(vehicle_id)
        braking_distance = speed * self.config.time_step_s + speed * speed / (2 * vehicles.getDecel(vehicle_id)) + 5
        if (target.edge_id == road_id and
                target.lane_position - vehicles.getLanePosition(vehicle_id) < braking_distance):
            if vehicles.isStopped(vehicle_id) and old is None:
                # A provider already parked near its first goal can stay there.
                current = self.providers[provider_id].position
                if current.distance_to(Position(target.x, target.y)) < 5:
                    self.targets[provider_id] = target
                    self.pending_targets.pop(provider_id, None)
                    return
            target = project_target(self.network, self.runtime.sumolib.geomhelper,
                                    position.x, position.y, excluded=road_id)
        if vehicles.isStopped(vehicle_id):
            vehicles.resume(vehicle_id)
            self.reinserting.add(vehicle_id)
        else:
            for stop in reversed(vehicles.getStops(vehicle_id)):
                stop_edge = self.connection.lane.getEdgeID(stop.lane)
                vehicles.setStop(vehicle_id, stop_edge, pos=stop.endPos, duration=0)
        vehicles.changeTarget(vehicle_id, target.edge_id)
        vehicles.setStop(vehicle_id, target.edge_id, pos=target.lane_position,
                         duration=self.config.steps * self.config.time_step_s + 3600,
                         flags=1)
        self.targets[provider_id] = target
        poi_id = f"target:{provider_id}"
        if provider_id not in self.target_pois:
            self.connection.poi.add(poi_id, target.x, target.y, (230, 185, 20, 255),
                                    poiType="provider-target", width=10, height=10)
            self.target_pois.add(provider_id)
        else:
            self.connection.poi.setPosition(poi_id, target.x, target.y)
        self.pending_targets.pop(provider_id, None)
        self.reroutes += 1
        self.target_events.append({
            "step": self.step_index, "provider": vehicle_id,
            "requested_x": position.x, "requested_y": position.y,
            "road_x": target.x, "road_y": target.y, "edge": target.edge_id,
            "lane_position": target.lane_position,
        })

    def _traffic_step(self) -> None:
        """Advance exactly one SUMO step and reject collisions or teleportation."""

        started = time.monotonic()
        self.connection.simulationStep()
        simulation = self.connection.simulation
        if simulation.getStartingTeleportNumber() or simulation.getCollidingVehiclesNumber():
            raise RuntimeError("SUMO reported a collision or teleport; inspect the episode's sumo.log.")
        remaining = self.gui_delay_s - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)

    def _sync_positions(self) -> None:
        """Copy SUMO lane positions, actual speed, and heading into Python nodes."""

        expected = {f"vehicle:{node.node_id}" for node in self.vehicles}
        expected.update(f"provider:{node.node_id}" for node in self.providers)
        active = set(self.connection.vehicle.getIDList())
        self.active_ids = active
        self.reinserting.difference_update(active)
        missing = expected - active - self.reinserting
        if missing or active - expected:
            raise RuntimeError(f"Traffic population changed: missing={sorted(missing)}.")
        for kind, nodes in (("vehicle", self.vehicles), ("provider", self.providers)):
            for node in nodes:
                vehicle_id = f"{kind}:{node.node_id}"
                if vehicle_id in self.reinserting:
                    # SUMO reports invalid coordinates during safe-gap insertion.
                    # The provider stays at its last actual parking position.
                    continue
                x, y = self.connection.vehicle.getPosition(vehicle_id)
                node.position = Position(x, y)
                if kind == "vehicle":
                    node.speed_mps = self.connection.vehicle.getSpeed(vehicle_id)
                    node.direction_rad = (90 - self.connection.vehicle.getAngle(vehicle_id)) * pi / 180

    def mobility_rows(self) -> list[dict]:
        """Return auditable actual positions and remaining road-target distance."""

        rows = []
        for kind, nodes in (("vehicle", self.vehicles), ("provider", self.providers)):
            for node in nodes:
                vehicle_id = f"{kind}:{node.node_id}"
                target = self.targets.get(node.node_id) if kind == "provider" else None
                distance = node.position.distance_to(Position(target.x, target.y)) if target else ""
                rows.append({
                    "step": self.step_index, "time_s": self.connection.simulation.getTime(),
                    "node": vehicle_id, "x": node.position.x, "y": node.position.y,
                    "speed_mps": 0.0 if vehicle_id in self.reinserting else self.connection.vehicle.getSpeed(vehicle_id),
                    "road": "" if vehicle_id in self.reinserting else self.connection.vehicle.getRoadID(vehicle_id),
                    "mobility_state": "waiting_reinsertion" if vehicle_id in self.reinserting else "on_network",
                    "target_distance_m": distance, "weather": self.weather,
                })
        return rows
