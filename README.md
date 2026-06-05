# Model Crossfire

Model Crossfire is a tiny file-queue bridge for making two coding agents work
together without GUI automation.

The intended pattern is:

```text
Lead agent writes a task file
  -> Claude Code executes the scoped task
  -> Claude writes a durable output file
  -> Codex reviews that output
  -> the human decides whether to continue
```

It is useful when you want a lead/reviewer agent and a secondary implementation
agent to collaborate without copying text between windows.

## Why Not GUI Automation?

Screen scraping and simulated clicks work, but they are brittle:

- wrong focus can paste prompts into the wrong window;
- coordinates break when the layout changes;
- long outputs are hard to capture reliably;
- a bad loop can trigger live chats repeatedly.

Model Crossfire uses files and CLI commands instead. One command processes one
task, and all inputs/outputs stay visible on disk.

## Requirements

- Python 3.10+
- Claude Code CLI available as `claude`
- Codex CLI available as `codex`

Check your environment:

```powershell
python model_crossfire.py doctor
```

## Quick Start

Queue a task for Claude:

```powershell
python model_crossfire.py queue claude --file examples\readonly_status_check.md --title status_check
```

Run one Claude task:

```powershell
python model_crossfire.py run-claude --cwd C:\path\to\project --permission-mode default
```

Relay the latest Claude output to Codex for review:

```powershell
python model_crossfire.py relay-claude-to-codex
```

Run one Codex review:

```powershell
python model_crossfire.py run-codex --cwd C:\path\to\project
```

## Directory Layout

```text
queue/
  to_claude/
  to_codex/
  processed/
out/
  claude/
  codex/
logs/
examples/
```

Generated queue, output, and log files are ignored by Git.

## Collaboration Model

Model Crossfire intentionally does not run an infinite autonomous loop.

The default loop is human-gated:

1. Create or queue a task.
2. Run Claude once.
3. Relay to Codex.
4. Run Codex once.
5. Read the result and decide the next step.

This keeps the lead agent in control and avoids uncontrolled agent chatter.

## Privacy Notes

Do not queue prompts containing credentials, cookies, API keys, private browser
profiles, or private screenshots. The bridge stores prompts and outputs as
plain UTF-8 files.

## Current Status

Proof of concept. Tested on Windows with Claude Code CLI and Codex CLI.
