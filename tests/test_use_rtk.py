import subprocess
import unittest
from unittest.mock import patch

from hooks import use_rtk


def shell_call(command, tool="Bash"):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command, "description": "Test command", "timeout": 1000},
    }


class HookTests(unittest.TestCase):
    def setUp(self):
        self.rtk = "/tools/rtk"
        which = patch.object(use_rtk.shutil, "which", return_value=self.rtk)
        run = patch.object(use_rtk.subprocess, "run")
        self.which = which.start()
        self.run = run.start()
        self.addCleanup(which.stop)
        self.addCleanup(run.stop)
        self.rewrite_result(1)

    def rewrite_result(self, status, stdout=""):
        self.run.return_value = subprocess.CompletedProcess([], status, stdout=stdout, stderr="")

    def denial(self, payload):
        result = use_rtk.handle(payload)["hookSpecificOutput"]
        self.assertEqual(result["hookEventName"], "PreToolUse")
        self.assertEqual(result["permissionDecision"], "deny")
        self.assertNotIn("updatedInput", result)
        return result["permissionDecisionReason"]

    def test_session_and_subagent_receive_guidance_when_rtk_exists(self):
        for event in ("SessionStart", "SubagentStart"):
            with self.subTest(event=event):
                result = use_rtk.handle({"hook_event_name": event})["hookSpecificOutput"]
                self.assertEqual(result["hookEventName"], event)
                self.assertIn("rtk bypass", result["additionalContext"])
        self.run.assert_not_called()

    def test_rtk_absent_leaves_valid_calls_and_session_start_to_claude(self):
        self.which.return_value = None
        for tool in ("Bash", "Monitor", "PowerShell"):
            with self.subTest(tool=tool):
                self.assertEqual(use_rtk.handle(shell_call("printf hello", tool)), {})
        self.assertEqual(use_rtk.handle({"hook_event_name": "SessionStart"}), {})
        self.run.assert_not_called()

    def test_other_tools_and_websocket_monitor_are_outside_shell_scope(self):
        self.assertEqual(use_rtk.handle(shell_call("git status", "Read")), {})
        watch = shell_call("", "Monitor")
        watch["tool_input"] = {"ws": {"url": "wss://example.com"}}
        self.assertEqual(use_rtk.handle(watch), {})
        self.run.assert_not_called()

    def test_explicit_rtk_calls_return_no_permission_override(self):
        commands = (
            "rtk --version",
            "rtk git status",
            "rtk bypass printf '%s\\n' 'literal; $(echo text)'",
            "rtk bypass printf '%s' '$money' > 'output file' 2>&1",
            "rtk bypass git status --porcelain | rtk bypass wc -l",
            "rtk git status &&\nrtk git log || rtk bypass printf '%s' fallback",
            "rtk ls; rtk git status\nrtk bypass printf '%s' done",
            "rtk run --shell bash -c 'value=$(printf text); printf \"%s\" \"$value\"'",
            "rtk run --shell bash -c 'cat <<EOF\nhello\nEOF'",
            "rtk run --shell bash -c 'printf '\"'\"'%s\n'\"'\"' text'",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(use_rtk.handle(shell_call(command)), {})
        self.run.assert_not_called()

    def test_raw_stages_and_expansions_require_rtk(self):
        for command in (
            "git status",
            "rtk git status | head",
            "rtk ls && printf hello",
            "rtk ls;\nprintf hello",
            "rtk ls & printf hello",
            "rtk bypass printf \"$(printf hello)\"",
            "rtk bypass printf `printf hello`",
            "rtk bypass cat <(printf hello)",
            "rtk bypass cat <<EOF\nhello\nEOF",
            "NAME=value rtk ls",
            "rtk\\\n-other ls",
            "rtk-other ls",
        ):
            with self.subTest(command=command):
                reason = self.denial(shell_call(command))
                self.assertIn("rtk run --shell bash -c", reason)

    def test_rewrite_exit_zero_and_three_suggest_complete_rtk_commands(self):
        for status in (0, 3):
            with self.subTest(status=status):
                self.rewrite_result(status, "rtk git status\n")
                reason = self.denial(shell_call("git status", "Monitor"))
                self.assertTrue(reason.endswith("\nrtk git status"))
                self.assertEqual(self.run.call_args.args[0], [self.rtk, "rewrite", "--", "git status"])

    def test_incomplete_rewrite_gets_general_routing_guidance(self):
        self.rewrite_result(3, "rtk git status | head\n")
        reason = self.denial(shell_call("git status | head"))
        self.assertIn("each pipeline or chain stage", reason)
        self.assertNotIn("rtk git status | head", reason)

    def test_rtk_denials_get_no_retry_suggestion(self):
        for detail in ("", "Blocked by pipeline rule"):
            with self.subTest(detail=detail):
                self.rewrite_result(2, detail)
                reason = self.denial(shell_call("git status"))
                self.assertIn("RTK denied this command", reason)
                self.assertTrue(reason.endswith(detail))
                self.assertNotIn("rtk run", reason)

    def test_rewrite_failures_keep_the_native_call_blocked(self):
        self.rewrite_result(70)
        self.assertIn("exited with status 70", self.denial(shell_call("printf hello")))
        for error in (OSError(), subprocess.TimeoutExpired("rtk", 2)):
            with self.subTest(error=error):
                self.run.side_effect = error
                self.assertIn("could not run", self.denial(shell_call("printf hello")))

    def test_powershell_uses_literal_rtk_stages_or_a_script_file(self):
        for command in (
            "rtk git status",
            "rtk run pwsh -NoProfile -File './a script.ps1'",
            "rtk bypass git status --porcelain | rtk bypass rg tracked",
            "rtk git status\r\n\r\nrtk git log",
        ):
            with self.subTest(command=command):
                self.assertEqual(use_rtk.handle(shell_call(command, "PowerShell")), {})
        for command in (
            "Get-Location",
            "rtk git status | Select-Object -First 1",
            'rtk bypass Write-Output "$(Get-Location)"',
            "rtk git status; & git log",
        ):
            with self.subTest(command=command):
                self.assertIn("-File", self.denial(shell_call(command, "PowerShell")))
        self.run.assert_not_called()

    def test_invalid_command_payload_is_blocked(self):
        for command in (None, [], "", " \n ", "rtk\x00"):
            with self.subTest(command=command):
                self.assertIn("valid shell command", self.denial(shell_call(command)))
        self.run.assert_not_called()
