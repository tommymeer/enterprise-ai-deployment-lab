"""Focused offline coverage for the one-case inspection script."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.run_offline_support_case import run


class OfflineSupportCaseScriptTest(unittest.TestCase):
    def test_one_scripted_case_reaches_successful_workflow_completion(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("network access attempted")):
            output = run()

        self.assertIn("status: complete", output)
        self.assertIn("Intake route: delivered_not_received_workflow", output)
        self.assertIn("Full DNR workflow entered: yes", output)
        self.assertIn("Disposition selected: approve_refund", output)
        self.assertIn("Execution result: succeeded", output)
        self.assertIn("Final case status: closed", output)
        self.assertIn("workflow_completed", output)


if __name__ == "__main__":
    unittest.main()
