import argparse
import json
import os
import shutil
import sys

from use_rtk import GUIDANCE, command_denial, deny, response


def as_object(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def working_directory(base, override=None):
    base = base if isinstance(base, str) and os.path.isabs(base) else None
    if isinstance(override, str) and override:
        if os.path.isabs(override):
            return override
        if base:
            return os.path.join(base, override)
    return base


def startup(host):
    if not shutil.which("rtk"):
        return {}
    if host == "cursor":
        return {"additional_context": GUIDANCE}
    if host == "antigravity":
        return {"injectSteps": [{"systemMessage": {"systemMessage": GUIDANCE}}]}
    if host == "copilot":
        return {"additionalContext": GUIDANCE}
    return response("SessionStart", additionalContext=GUIDANCE)


def decision(host, reason=None):
    if host == "cursor":
        if reason:
            return {"permission": "deny", "user_message": "Use RTK blocked a shell command.", "agent_message": reason}
        return {"permission": "allow"}
    if reason:
        if host in ("antigravity", "gemini"):
            return {"decision": "deny", "reason": reason}
        if host == "copilot":
            return {"permissionDecision": "deny", "permissionDecisionReason": reason}
        return deny(reason)
    return {"decision": "allow"} if host == "antigravity" else {}


def shell_call(host, payload):
    """Translate each host's shell-hook payload without changing its tool input."""
    base = payload.get("cwd")
    windows = sys.platform == "win32"
    if host == "cursor":
        reason = command_denial(payload.get("command"), powershell=windows, cwd=working_directory(base))
        return decision(host, reason)

    if host == "antigravity":
        call = as_object(payload.get("toolCall"))
        if call.get("name") != "run_command":
            return decision(host)
        args = as_object(call.get("args"))
        reason = command_denial(args.get("CommandLine"), cwd=working_directory(None, args.get("Cwd")))
        return decision(host, reason)

    if host == "copilot":
        tool = payload.get("toolName")
        if tool not in ("bash", "powershell"):
            return {}
        args = as_object(payload.get("toolArgs"))
        cwd = working_directory(base, args.get("cwd"))
        reason = command_denial(args.get("command"), powershell=tool == "powershell", cwd=cwd)
        return decision(host, reason)

    args = as_object(payload.get("tool_input"))
    if host == "gemini":
        if payload.get("tool_name") != "run_shell_command":
            return {}
        cwd = working_directory(base, args.get("dir_path"))
        reason = command_denial(args.get("command"), powershell=windows, cwd=cwd)
        return decision(host, reason)

    if payload.get("tool_name") != "Bash":
        return {}
    cwd = working_directory(base, args.get("workdir"))
    reason = command_denial(args.get("command"), powershell=windows, cwd=cwd)
    return decision(host, reason)


def main():
    parser = argparse.ArgumentParser(description="Use RTK agent hook")
    parser.add_argument("host", choices=("codex", "cursor", "antigravity", "gemini", "copilot"))
    parser.add_argument("event", choices=("startup", "shell"))
    options = parser.parse_args()
    if options.event == "startup":
        json.load(sys.stdin)
        result = startup(options.host)
    else:
        try:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
        except ValueError:
            result = decision(options.host, "Use RTK requires a valid shell tool input.")
        else:
            result = shell_call(options.host, payload)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
