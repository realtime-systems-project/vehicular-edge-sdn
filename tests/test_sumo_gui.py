"""Regression checks for stale XQuartz sockets and early GUI failure."""

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from sumo_experiment.gui import prepare_gui, working_display


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
                patch("sumo_experiment.gui.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "sudo install -d"):
                prepare_gui()
            run.assert_not_called()

    def test_other_platforms_do_not_require_xquartz(self) -> None:
        """Windows and Linux GUI startup must not depend on Mac utilities."""

        with patch("sumo_experiment.gui.sys.platform", "win32"), \
                patch("sumo_experiment.gui.subprocess.run") as run:
            prepare_gui()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
