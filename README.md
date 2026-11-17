# Use RTK for Claude Code

This plugin enforces the command routing policy from the [Use RTK skill](https://github.com/rogervila/agent-skills/blob/main/skills/use-rtk/SKILL.md). When `rtk` is on `PATH`, Claude Code shell calls must invoke it. The plugin gives Claude the routing instructions at session and subagent startup.

## Install

Use Claude Code 2.1.314 or later for Bash, shell-backed Monitor, and PowerShell coverage. Install Python 3.8 or later as `python3` and [RTK](https://github.com/rtk-ai/rtk) with `rewrite`, `run --shell`, and `bypass` support. RTK 1.2.0 was used for testing. Both executables must be on the `PATH` Claude Code inherits.

Try the local checkout from its root:

```sh
claude --plugin-dir .
```

For persistent installation, run these commands inside Claude Code. Use the absolute path to the checkout, then reload plugins or start a new session.

```text
/plugin marketplace add /absolute/path/to/use-rtk-plugin
/plugin install use-rtk@use-rtk-plugin
/reload-plugins
```

Use RTK installs its own `PreToolUse` hook through the plugin. `rtk init --global` is optional.

## Behavior

| Need | Example |
| --- | --- |
| Filtered output | `rtk git status` |
| No dedicated wrapper | `rtk run --shell bash -c 'printf "%s\n" hello'` |
| Exact bytes or streaming | `rtk bypass git diff` |
| Pipeline with machine-readable output | `rtk bypass git status --porcelain \| rtk bypass wc -l` |
| Shell expansion, assignments, or heredocs | `rtk run --shell bash -c 'value=$(git rev-parse --short HEAD); printf "%s\n" "$value"'` |
| Complex PowerShell script | `rtk run pwsh -NoProfile -File ./script.ps1` |

If Claude requests `git status`, the plugin blocks the call and suggests `rtk git status`. A call with a native pipeline stage is also blocked. Explicit RTK calls continue through Claude Code’s permission checks. Define permission rules for the RTK invocations your policy intends to allow, deny, or prompt for, since Claude Code matches the submitted command text. Use RTK is a routing policy at the tool-call boundary. Programs launched by RTK control their own subprocesses.

If `rtk` is absent, shell calls continue through Claude Code’s ordinary permission flow. Use your terminal for applications that require an interactive TTY. For a persistent directory change, use Claude Code’s `/cd`. A `cd` inside `rtk run` applies to that child shell. For shell-backed Monitor streams, prefer `rtk bypass` to keep output unfiltered.

## Verify

```sh
claude plugin validate --strict .claude-plugin/plugin.json
claude plugin validate --strict .claude-plugin/marketplace.json
rtk bypass python3 -B -m unittest discover -s tests -v
```

The plugin layout follows the [Caveman plugin](https://github.com/juliusbrussee/caveman). See the [Claude Code hooks reference](https://code.claude.com/docs/en/hooks#pretooluse-decision-control) for tool-call decisions.
