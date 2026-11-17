import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_FILES = {
    "codex": (".codex-plugin/plugin.json", "PreToolUse", "SessionStart"),
    "cursor": (".cursor-plugin/plugin.json", "beforeShellExecution", "sessionStart"),
    "copilot": (".plugin/plugin.json", "preToolUse", "sessionStart"),
    "antigravity": (".antigravity-plugin/plugin.json", "PreToolUse", "SessionStart"),
    "gemini": ("gemini-extension.json", "BeforeTool", "SessionStart"),
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@unittest.skipIf(sys.platform == "win32", "These tests exercise the Unix hook launch commands.")
class HostHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="use-rtk test ")
        cls.addClassCleanup(temporary.cleanup)
        cls.scratch = Path(temporary.name)
        cls.gemini = cls.scratch / "use-rtk"
        subprocess.run([sys.executable, str(ROOT / "scripts/package-gemini.py"), str(cls.gemini)],
                       check=True, capture_output=True, timeout=5)

        cls.bin = cls.scratch / "bin"
        cls.bin.mkdir()
        (cls.bin / "python3").symlink_to(sys.executable)
        cls.rtk_bin = cls.scratch / "rtk-bin"
        cls.rtk_bin.mkdir()
        rtk = cls.rtk_bin / "rtk"
        rtk.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "status, stdout = json.loads(os.environ['USE_RTK_TEST_REWRITE'])\n"
            "Path(os.environ['USE_RTK_TEST_LOG']).write_text(json.dumps([os.getcwd(), *sys.argv[1:]]))\n"
            "print(stdout, end='')\n"
            "sys.exit(status)\n",
            encoding="utf-8",
        )
        rtk.chmod(0o755)

    def hook(self, host, event):
        manifest_file, shell_event, startup_event = PLUGIN_FILES[host]
        root = self.gemini if host == "gemini" else ROOT
        manifest = read_json(root / manifest_file)
        self.assertEqual(manifest["name"], "use-rtk")
        if host == "antigravity":
            config = read_json(root / "hooks.json")["use-rtk"]
        else:
            config = read_json(root / manifest.get("hooks", "hooks/hooks.json"))["hooks"]
        handler, = config[startup_event if event == "startup" else shell_event]
        if "hooks" in handler:
            handler, = handler["hooks"]

        if "exec" in handler:
            args = [arg.replace("${PLUGIN_ROOT}", str(root)) for arg in handler.get("args", [])]
            return root, [handler["exec"], *args]
        command = handler["command"].replace("${extensionPath}", str(root))
        return root, ["/bin/sh", "-c", command]

    def run_hook(self, host, event, payload, *, rtk=True, rewrite=(3, "rtk git status\n")):
        root, argv = self.hook(host, event)
        log = self.scratch / "rewrite-log.json"
        log.unlink(missing_ok=True)
        path = os.pathsep.join(map(str, (self.bin, self.rtk_bin) if rtk else (self.bin,)))
        env = dict(os.environ, PATH=path, PLUGIN_ROOT=str(root), USE_RTK_TEST_LOG=str(log),
                   USE_RTK_TEST_REWRITE=json.dumps(rewrite))
        result = subprocess.run(argv, cwd=root, env=env, input=payload, text=True, capture_output=True,
                                timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout), read_json(log) if log.exists() else None

    def payload(self, host, command):
        cwd = str(self.scratch)
        if host == "cursor":
            return {"command": command, "cwd": cwd}
        if host == "antigravity":
            return {"toolCall": {"name": "run_command", "args": {"CommandLine": command, "Cwd": cwd}}}
        if host == "copilot":
            return {"toolName": "bash", "toolArgs": json.dumps({"command": command}), "cwd": cwd}
        tool = "Bash" if host == "codex" else "run_shell_command"
        return {"hook_event_name": "PreToolUse" if host == "codex" else "BeforeTool",
                "tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}

    def reason(self, host, result):
        if host in ("antigravity", "gemini"):
            self.assertEqual(result["decision"], "deny")
            return result["reason"]
        if host == "cursor":
            self.assertEqual(result["permission"], "deny")
            return result["agent_message"]
        if host == "codex":
            result = result["hookSpecificOutput"]
        self.assertEqual(result["permissionDecision"], "deny")
        return result["permissionDecisionReason"]

    def expected_pass(self, host):
        return {"cursor": {"permission": "allow"}, "antigravity": {"decision": "allow"}}.get(host, {})

    def test_native_calls_are_blocked_with_a_complete_rtk_retry(self):
        for host in PLUGIN_FILES:
            with self.subTest(host=host):
                result, invocation = self.run_hook(host, "shell", json.dumps(self.payload(host, "git status")))
                self.assertTrue(self.reason(host, result).endswith("\nrtk git status"))
                self.assertEqual(invocation, [str(self.scratch), "rewrite", "--", "git status"])

    def test_native_pipeline_stage_and_rtk_denials(self):
        for host in PLUGIN_FILES:
            with self.subTest(host=host):
                command = "rtk git status | head"
                result, _ = self.run_hook(host, "shell", json.dumps(self.payload(host, command)),
                                          rewrite=(3, command))
                self.assertIn("each pipeline or chain stage", self.reason(host, result))
                result, _ = self.run_hook(host, "shell", json.dumps(self.payload(host, command)),
                                          rewrite=(2, "Test RTK rule"))
                self.assertTrue(self.reason(host, result).endswith("Test RTK rule"))

    def test_explicit_rtk_and_missing_rtk_follow_the_host_flow(self):
        for host in PLUGIN_FILES:
            for rtk, command in ((True, "rtk git status | rtk bypass head"), (False, "git status")):
                with self.subTest(host=host, rtk=rtk):
                    result, invocation = self.run_hook(host, "shell", json.dumps(self.payload(host, command)), rtk=rtk)
                    self.assertEqual(result, self.expected_pass(host))
                    self.assertIsNone(invocation)

    def test_startup_context_and_malformed_shell_payloads(self):
        for host in PLUGIN_FILES:
            with self.subTest(host=host):
                result, _ = self.run_hook(host, "startup", "{}")
                self.assertIn("RTK is available", json.dumps(result))
                result, _ = self.run_hook(host, "startup", "{}", rtk=False)
                self.assertEqual(result, {})
                result, _ = self.run_hook(host, "shell", "[]")
                self.assertIn("valid shell tool input", self.reason(host, result))

    def test_copilot_powershell_expansions_require_an_explicit_wrapper(self):
        payload = {"toolName": "powershell", "toolArgs": {"command": 'rtk bypass echo "$(Get-Location)"'}}
        result, invocation = self.run_hook("copilot", "shell", json.dumps(payload))
        self.assertIn("-File", self.reason("copilot", result))
        self.assertIsNone(invocation)
