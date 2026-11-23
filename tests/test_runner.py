import sys
import unittest
from unittest import mock

from lanparty.runner import CommandError, Runner


@mock.patch("lanparty.runner.WAIT_INTERVAL_SECONDS", 0.05)
class OnWaitTest(unittest.TestCase):
    """Runs a real (tiny) Python process, because this is about waiting for a process."""

    def test_on_wait_is_called_while_the_command_runs(self):
        waited = []
        result = Runner().run([sys.executable, "-c", "import time; time.sleep(0.4)"], on_wait=waited.append)
        self.assertEqual(result.returncode, 0)
        self.assertGreaterEqual(len(waited), 2)
        self.assertEqual(waited, sorted(waited))

    def test_exit_code_is_returned(self):
        result = Runner().run([sys.executable, "-c", "raise SystemExit(3)"], check=False, on_wait=lambda _: None)
        self.assertEqual(result.returncode, 3)
        with self.assertRaises(CommandError):
            Runner().run([sys.executable, "-c", "raise SystemExit(3)"], on_wait=lambda _: None)

    def test_timeout_stops_the_command(self):
        with self.assertRaises(CommandError) as caught:
            Runner().run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2, on_wait=lambda _: None)
        self.assertIn("did not finish", str(caught.exception))

    def test_missing_command(self):
        with self.assertRaises(CommandError):
            Runner().run(["lanparty-no-such-command"], on_wait=lambda _: None)


if __name__ == "__main__":
    unittest.main()
