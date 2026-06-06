---
name: agent-relay
description: >
  Multi-agent collaboration via file-queue workbench. Use when delegating work
  to secondary models, reducing lead-model token usage, setting up worker
  queues, or implementing review flows between agents. Triggers for:
  multi-agent coordination, splitting work across models, Claude-Codex relay,
  worker task queues, scoped agent delegation, and cross-model review pipelines.
---

# AgentRelay

File-queue bridge for multi-agent CLI collaboration. A lead model writes scoped
task files, workers process them one at a time through CLI tools, and durable
reports land in `out/<worker>/` for review.

## When to reach for AgentRelay

- The lead model wants to **offload scoped work** to cheaper or secondary models
- You need **independent workers** running read-only research, test execution,
  or first-draft documentation
- You want **review gates** — worker output is never auto-accepted; a lead
  reviews before trusting
- You're building a **multi-worker pipeline** (researcher → implementer → reviewer)

## Quick start

```powershell
# Check the environment
python agent_relay.py doctor

# Queue a task for a worker
python agent_relay.py queue claude-research --file tasks/research.md --role "read-only researcher"

# Run one queued task
python agent_relay.py run-worker --worker claude-research --backend claude --cwd C:\path\to\project

# Relay output to reviewer
python agent_relay.py relay-worker --source-worker claude-research --target-worker codex

# Run reviewer
python agent_relay.py run-worker --worker codex --backend codex --cwd C:\path\to\project

# Show state
python agent_relay.py status
```

## Worker commands reference

See `references/commands.md` for all CLI commands and flags.

## Safety rules

- Prefer **read-only** worker tasks.
- Require **reports** for every worker task.
- Never queue secrets, cookies, browser profiles, or API keys.
- Worker outputs are **never** auto-merged into production work.
- Avoid concurrent workers that edit the same files.

## Multi-worker pattern

Independent read-only work can be fanned out across workers, then reviewed:

```text
claude-research  → research report → out/claude-research/
claude-impl      → implementation  → out/claude-impl/
codex            → review + merge  → out/codex/
```

Queue tasks independently, run workers in separate terminals when tasks don't
write the same files, then relay all outputs to a reviewer.

## File layout

```text
queue/to_<worker>/    # pending task files
queue/processed/      # completed task files
out/<worker>/         # worker output reports
logs/                 # JSON run logs
locks/                # worker mutex files
```
