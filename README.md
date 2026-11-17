# Use RTK for coding agents

Use RTK packages the command routing policy from the [Use RTK skill](https://github.com/rogervila/agent-skills/blob/main/skills/use-rtk/SKILL.md) for Claude Code, Codex, Cursor, Google Antigravity, Gemini CLI, and GitHub Copilot CLI. When `rtk` is on `PATH`, the host's shell hook requires it and gives the agent a retry suggestion when a command is blocked.

## Prerequisites

Install Python 3.8 or later as `python3` and [RTK](https://github.com/rtk-ai/rtk) with `rewrite`, `run --shell`, and `bypass` support. RTK 1.2.0 was used for testing. Both executables must be on the `PATH` inherited by the agent. Each package includes its own hook, so `rtk init` is optional.

## Install

- [Claude Code](#claude-code)
- [Codex](#codex)
- [Cursor desktop and CLI](#cursor)
- [Google Antigravity (`agy`)](#google-antigravity)
- [Gemini CLI](#gemini-cli)
- [GitHub Copilot CLI](#github-copilot-cli)

For Cursor, Gemini CLI, or any local checkout instructions below, clone the repository and run the commands from its root. If you already have a checkout, use that directory.

```sh
git clone https://github.com/rogervila/use-rtk-plugin.git
cd use-rtk-plugin
```

Use the checkout instructions to install changes that are still local.

## Claude Code

Use Claude Code 2.1.314 or later for Bash, shell-backed Monitor, and PowerShell coverage. Run these commands inside a Claude Code session.

```text
/plugin marketplace add rogervila/use-rtk-plugin
/plugin install use-rtk@use-rtk-plugin
/reload-plugins
```

To install from your terminal, run the commands below, then start Claude Code. In an open session, run `/reload-plugins` to load the plugin.

```sh
claude plugin marketplace add rogervila/use-rtk-plugin
claude plugin install use-rtk@use-rtk-plugin
```

From the checkout root, load the Claude Code plugin for one session.

```sh
claude --plugin-dir .
```

## Codex

Add the repository marketplace and install the plugin.

```sh
codex plugin marketplace add rogervila/use-rtk-plugin
codex plugin add use-rtk@use-rtk-plugin
```

To install from the checkout root, run the following commands.

```sh
codex plugin marketplace add .
codex plugin add use-rtk@use-rtk-plugin
```

Start a new Codex session and review and trust the plugin hooks via `/hooks`. See [Codex plugin-bundled hooks](https://learn.chatgpt.com/docs/hooks#plugin-bundled-hooks).

## Cursor

In Cursor, open **Customize → Plugins → Import from Disk**, select the checkout root, and reload Cursor. You can also copy the checkout to `~/.cursor/plugins/local/use-rtk` and reload the window. Inspect the active hooks under **Customize → Hooks**. See [Cursor plugin setup](https://cursor.com/docs/plugins#test-plugins-locally).

For a Cursor CLI session, run `agent --plugin-dir .` from the checkout root.

## Google Antigravity

Install via `agy`, then start a new session.

```sh
agy plugin install https://github.com/rogervila/use-rtk-plugin
```

From a local checkout use `agy plugin install .`. Verify with `agy plugin list`. See [Antigravity plugin installation](https://antigravity.google/docs/marketplace/#install-from-your-shell-agy-plugin).

## Gemini CLI

From the checkout root, build the extension into a new directory and install it.

```sh
python3 scripts/package-gemini.py ./build/use-rtk
gemini extensions install ./build/use-rtk
```

Review the extension at the install prompt and restart Gemini CLI. Verify with `gemini extensions list`. See the [Gemini CLI extension reference](https://geminicli.com/docs/extensions/reference/).

## GitHub Copilot CLI

Add the repository marketplace and install the plugin.

```sh
copilot plugin marketplace add rogervila/use-rtk-plugin
copilot plugin install use-rtk@use-rtk-plugin
```

To install from the checkout root, run the following commands.

```sh
copilot plugin marketplace add .
copilot plugin install use-rtk@use-rtk-plugin
```

Restart the session to load the plugin. See the [Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).

## Behavior

| Need | Example |
| --- | --- |
| Filtered output | `rtk git status` |
| No dedicated wrapper | `rtk run --shell bash -c 'printf "%s\n" hello'` |
| Exact bytes or streaming | `rtk bypass git diff` |
| Pipeline with machine-readable output | `rtk bypass git status --porcelain \| rtk bypass wc -l` |
| Shell expansion, assignments, or heredocs | `rtk run --shell bash -c 'value=$(git rev-parse --short HEAD); printf "%s\n" "$value"'` |
| Complex PowerShell script | `rtk run pwsh -NoProfile -File ./script.ps1` |

If the agent requests `git status`, the plugin blocks the call and suggests `rtk git status`. A call with a native pipeline stage is also blocked. The agent submits the RTK command as a new tool call, so the host evaluates its permission rules against that command. Use RTK is a routing policy at the shell-tool boundary. Programs launched by RTK control their own subprocesses.

If `rtk` is absent, shell calls continue through the host’s ordinary permission flow. Runtime coverage depends on the host loading and running the hook. Use your terminal for applications that require an interactive TTY. A `cd` inside `rtk run` applies to that child shell. In Claude Code, use `/cd` for a persistent directory change and prefer `rtk bypass` for unfiltered Monitor streams.

## Verify

```sh
claude plugin validate --strict .claude-plugin/plugin.json
claude plugin validate --strict .claude-plugin/marketplace.json
rtk bypass python3 -B -m unittest discover -s tests -v
```

The plugin layout follows the [Caveman plugin](https://github.com/juliusbrussee/caveman). See the [Claude Code hooks reference](https://code.claude.com/docs/en/hooks#pretooluse-decision-control) for tool-call decisions.
