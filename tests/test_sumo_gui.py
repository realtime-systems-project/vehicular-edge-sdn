"""Regression checks for stale XQuartz sockets and early GUI failure."""

import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

from sumo_experiment.gui import (prepare_gui, working_display, write_view_settings,
                                 recover_local_authority, local_server_authority)
from sumo_experiment.environment import SumoEnvironment


class GuiPreflightTests(unittest.TestCase):
    """Verify display selection without needing a graphical desktop in tests."""

    @patch.dict(os.environ, {"DISPLAY": "/tmp/stale-socket"})
    def test_stale_shell_display_uses_working_launchd_display(self) -> None:
        """An old Terminal socket must not override a verified live display."""

        results = [subprocess.CompletedProcess([], 0, stdout="/tmp/current-socket\n"),
                   subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]
        with patch("sumo_experiment.gui.subprocess.run", side_effect=results) as run:
            address = working_display(Path("/opt/X11/bin/xdpyinfo"))
        self.assertEqual(address, "/tmp/current-socket")
        self.assertEqual(os.environ["DISPLAY"], address)
        self.assertEqual(run.call_args_list[-1].args[0][-1], address)

    @patch.dict(os.environ, {"DISPLAY": "/tmp/already-working"})
    def test_working_user_display_is_preserved(self) -> None:
        """A successful explicitly configured display takes precedence."""

        results = [subprocess.CompletedProcess([], 0, stdout="/tmp/other-socket\n"),
                   subprocess.CompletedProcess([], 0)]
        with patch("sumo_experiment.gui.subprocess.run", side_effect=results):
            self.assertEqual(working_display(Path("probe")), "/tmp/already-working")

    def test_missing_socket_directory_reports_admin_repair(self) -> None:
        """Detect the actual reported failure before attempting a GUI launch."""

        with patch("sumo_experiment.gui.sys.platform", "darwin"), \
                patch("sumo_experiment.gui.Path.is_file", return_value=True), \
                patch("sumo_experiment.gui.Path.is_dir", return_value=False), \
                patch("sumo_experiment.gui.working_display", return_value=None), \
                patch("sumo_experiment.gui.recover_local_authority", return_value=False), \
                patch("sumo_experiment.gui.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "sudo install -d"):
                prepare_gui()
            run.assert_not_called()

    def test_private_same_user_server_file_is_required(self) -> None:
        """Never reuse credentials from a publicly readable authority file."""

        with tempfile.TemporaryDirectory() as directory:
            authority = Path(directory) / "authority"
            authority.touch(mode=0o600)
            command = f'/opt/X11/bin/Xquartz :0 -nolisten tcp -auth "{authority}"\n'
            with patch("sumo_experiment.gui.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, stdout=command)):
                self.assertEqual(local_server_authority(), (":0", authority))
                authority.chmod(0o644)
                self.assertIsNone(local_server_authority())

    def test_verified_recovery_does_not_restart_xquartz(self) -> None:
        """A recovered connection should proceed directly without restarting the desktop."""

        with patch("sumo_experiment.gui.sys.platform", "darwin"), \
                patch("sumo_experiment.gui.Path.is_file", return_value=True), \
                patch("sumo_experiment.gui.working_display", return_value=None), \
                patch("sumo_experiment.gui.recover_local_authority", return_value=True), \
                patch("sumo_experiment.gui.subprocess.run") as run:
            prepare_gui()
            run.assert_not_called()

    def test_hostname_recovery_is_private_and_verified(self) -> None:
        """Keep the existing cookie off argv and use it only after a successful probe."""

        results = [subprocess.CompletedProcess([], 0, stdout=
                   "old-host/unix:0 MIT-MAGIC-COOKIE-1 " + "a" * 32 + "\n"),
                   subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0)]
        with patch.dict(os.environ, {"DISPLAY": "old-display", "XAUTHORITY": "old-authority"}), \
                patch("sumo_experiment.gui.local_server_authority", return_value=(":0", Path("server"))), \
                patch("sumo_experiment.gui.socket.gethostname", return_value="new-host"), \
                patch("sumo_experiment.gui.subprocess.run", side_effect=results) as run, \
                patch("sumo_experiment.gui.atexit.register") as register:
            self.assertTrue(recover_local_authority(Path("probe")))
            target = Path(os.environ["XAUTHORITY"])
            try:
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
                add = run.call_args_list[1]
                self.assertNotIn("a" * 32, str(add.args))
                self.assertIn("new-host/unix:0", add.kwargs["input"])
                self.assertEqual(os.environ["DISPLAY"], ":0")
                self.assertEqual(run.call_args.kwargs["env"]["XAUTHORITY"], str(target))
            finally:
                register.call_args.args[0]()
            self.assertFalse(target.exists())

    def test_failed_recovery_restores_environment_and_removes_file(self) -> None:
        """A rejected token must not poison the caller's environment or leave it on disk."""

        results = [subprocess.CompletedProcess([], 0, stdout=
                   "old-host/unix:0 MIT-MAGIC-COOKIE-1 " + "b" * 32 + "\n"),
                   subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
        with patch.dict(os.environ, {"DISPLAY": "old", "XAUTHORITY": "original"}), \
                patch("sumo_experiment.gui.local_server_authority", return_value=(":0", Path("server"))), \
                patch("sumo_experiment.gui.subprocess.run", side_effect=results) as run:
            self.assertFalse(recover_local_authority(Path("probe")))
            self.assertEqual(os.environ["DISPLAY"], "old")
            self.assertEqual(os.environ["XAUTHORITY"], "original")
            target = Path(run.call_args.kwargs["env"]["XAUTHORITY"])
            self.assertFalse(target.parent.exists())

    def test_other_platforms_do_not_require_xquartz(self) -> None:
        """Windows and Linux GUI startup must not depend on Mac utilities."""

        with patch("sumo_experiment.gui.sys.platform", "win32"), \
                patch("sumo_experiment.gui.subprocess.run") as run:
            prepare_gui()
            run.assert_not_called()

    def test_visible_car_symbols_do_not_change_vehicle_physics(self) -> None:
        """Vehicle enlargement belongs to view settings, not road/vehicle dimensions."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "view.xml"
            write_view_settings(path)
            vehicles = ET.parse(path).find("scheme/vehicles")
            self.assertEqual(vehicles.get("vehicle_exaggeration"), "6")
            self.assertNotIn("length", vehicles.attrib)
            self.assertNotIn("maxSpeed", vehicles.attrib)

    def test_playback_delay_only_sleeps_for_missing_time(self) -> None:
        """A fast TraCI step needs pacing, but an already delayed step does not."""

        environment = SumoEnvironment.__new__(SumoEnvironment)
        environment.connection = MagicMock()
        environment.connection.simulation.getStartingTeleportNumber.return_value = 0
        environment.connection.simulation.getCollidingVehiclesNumber.return_value = 0
        environment.gui_delay_s = 0.2
        with patch("sumo_experiment.environment.time.monotonic", side_effect=[10, 10.05]), \
                patch("sumo_experiment.environment.time.sleep") as sleep:
            environment._traffic_step()
            self.assertAlmostEqual(sleep.call_args.args[0], 0.15)
        with patch("sumo_experiment.environment.time.monotonic", side_effect=[10, 10.3]), \
                patch("sumo_experiment.environment.time.sleep") as sleep:
            environment._traffic_step()
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
