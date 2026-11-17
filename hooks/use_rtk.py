import json
import os
import re
import shutil
import subprocess
import sys


GUIDANCE = """RTK is available. Use it for every agent shell command,
including each stage of pipelines and command chains.
- Prefer a dedicated RTK wrapper, such as `rtk git status` or `rtk pytest`.
  Use `rtk rewrite -- '<command>'` to find a wrapper. Exit 0 or 3 returns a candidate,
  1 means use a general wrapper, and 2 means stop. Follow the host's permission prompts.
- Use `rtk test`, `rtk err`, or `rtk summary` where appropriate. For other commands or
  Bash syntax such as assignments, substitutions, and heredocs, use
  `rtk run --shell bash -c '<script>'` with a correctly single-quoted script.
- Use `rtk bypass <command>` for exact bytes, machine-readable output, streaming output,
  or when filtering loses required information. To apply a downstream filter, use
  `rtk bypass <producer> | rtk pipe -f <filter>`. Use `rtk recall <hash>` for recovery hints.
- For complex PowerShell syntax, put the script in a .ps1 file and run it with
  `rtk run pwsh -NoProfile -File <script.ps1>` or use powershell.exe for Windows PowerShell.
  Use the user's terminal for applications that require an interactive TTY."""

BASH_FALLBACK = (
    "Use a dedicated RTK wrapper for each pipeline or chain stage. "
    "For shell syntax such as substitutions, assignments, or heredocs, "
    "use `rtk run --shell bash -c '<script>'` with the entire script "
    "correctly single-quoted. Use `rtk bypass <command>` for raw output."
)
POWERSHELL_FALLBACK = (
    "Use an explicit RTK wrapper for each pipeline or chain stage. "
    "For complex PowerShell syntax, run a script file through "
    "`rtk run pwsh -NoProfile -File <script.ps1>` "
    "or use powershell.exe for Windows PowerShell."
)

# Recognize only literal shell words, simple redirections, and command separators.
# Anything that might execute outside RTK needs an explicit wrapper around it.
BASH_TOKENS = re.compile(
    r"""(?P<space>[ \t]+)
    |(?P<redirect>&>>?|[0-9]*(?:>>|>\||>&|<&|<>|>|<))
    |(?P<separator>\|\||\|&|&&|[;|&\n])
    |(?P<word>(?:[^\s\x00'"\\`$\#;&|<>()]|'[^'\x00]*'|"(?:[^"\\`$\x00]|\\[^\x00])*"|\\[^\n\x00])+)
    """,
    re.VERBOSE,
)
POWERSHELL_TOKENS = re.compile(
    r"""(?P<space>[ \t]+)
    |(?P<redirect>[1-6*]?>&|[1-6*]?>>?)
    |(?P<separator>\|\||&&|\r?\n|[;|])
    |(?P<word>(?:[a-zA-Z0-9_./:\\=+%~-]|'[^'‘’\x00]*'|"[^"“”`$\x00]*")+)
    """,
    re.VERBOSE,
)


def uses_rtk(command, tokens):
    """Check that every top-level invocation begins with the literal RTK executable."""
    offset = 0
    needs_command = True
    needs_target = False
    saw_rtk = False

    while offset < len(command):
        match = tokens.match(command, offset)
        if match is None:
            return False

        offset = match.end()
        kind, value = match.lastgroup, match.group()
        if kind == "space":
            continue
        if needs_target:
            if kind != "word":
                return False
            needs_target = False
        elif kind == "separator":
            if needs_command and not value.endswith("\n"):
                return False
            needs_command = True
        elif needs_command:
            if kind != "word" or value != "rtk":
                return False
            saw_rtk = True
            needs_command = False
        elif kind == "redirect":
            needs_target = True

    return saw_rtk and not needs_target


def response(event, **fields):
    return {"hookSpecificOutput": {"hookEventName": event, **fields}}


def deny(reason):
    return response("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)


def bash_denial(rtk, command, cwd):
    try:
        rewrite = subprocess.run(
            [rtk, "rewrite", "--", command],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return f"RTK is required, but `rtk rewrite` could not run. {BASH_FALLBACK}"

    candidate = rewrite.stdout.strip()
    if rewrite.returncode == 2:
        reason = "RTK denied this command. Do not retry it through another wrapper."
        return f"{reason}\n{candidate}" if candidate else reason
    if rewrite.returncode in (0, 1, 3):
        if rewrite.returncode != 1 and uses_rtk(candidate, BASH_TOKENS):
            return f"RTK is required. Retry the shell call with this RTK command:\n{candidate}"
        return f"RTK is required. {BASH_FALLBACK}"
    return f"RTK is required. `rtk rewrite` exited with status {rewrite.returncode}. {BASH_FALLBACK}"


def command_denial(command, *, powershell=False, cwd=None):
    """Return the reason to block a shell command, or leave it to the host."""
    if not isinstance(command, str) or not command.strip() or "\x00" in command:
        return "Use RTK requires a valid shell command string."

    rtk = shutil.which("rtk")
    if not rtk:
        return None
    if powershell:
        return None if uses_rtk(command, POWERSHELL_TOKENS) else f"RTK is required. {POWERSHELL_FALLBACK}"
    return None if uses_rtk(command, BASH_TOKENS) else bash_denial(os.path.abspath(rtk), command, cwd)


def handle(payload):
    event = payload.get("hook_event_name")
    if event in ("SessionStart", "SubagentStart"):
        return response(event, additionalContext=GUIDANCE) if shutil.which("rtk") else {}
    if event != "PreToolUse":
        return {}

    tool = payload.get("tool_name")
    if tool not in ("Bash", "Monitor", "PowerShell"):
        return {}
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return deny("Use RTK requires a valid shell tool input.")
    if tool == "Monitor" and "command" not in tool_input and "ws" in tool_input:
        return {}
    reason = command_denial(tool_input.get("command"), powershell=tool == "PowerShell")
    return deny(reason) if reason else {}


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    print(json.dumps(handle(payload)))
