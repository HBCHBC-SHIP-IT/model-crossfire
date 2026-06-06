# AgentRelay CLI Commands

## Environment check

```powershell
python agent_relay.py doctor
```

## Queue a task

```powershell
python agent_relay.py queue <worker> --file <path> [--title <title>] [--role <role>] [--raw]
```

| Flag | Purpose |
|------|---------|
| `--file` | Path to prompt file (required) |
| `--title` | Task title (default: filename stem) |
| `--role` | Worker role description |
| `--raw` | Queue prompt as-is, no metadata envelope |

## Run workers

```powershell
# Named worker with explicit backend
python agent_relay.py run-worker --worker <name> --backend claude|codex [--cwd <path>] [--timeout <s>]

# Legacy two-agent commands
python agent_relay.py run-claude [--worker <name>] [--cwd <path>]
python agent_relay.py run-codex [--worker <name>] [--cwd <path>]
```

Claude backend flags:
- `--permission-mode` — default, acceptEdits, bypassPermissions, plan
- `--dangerously-skip-permissions` — bypass permission prompts
- `--add-dir` — extra directory access

Codex backend flags:
- `--sandbox` — workspace-write (default)

## Relay between workers

```powershell
# Relay latest Claude output to Codex
python agent_relay.py relay-claude-to-codex

# Relay any worker to any other worker
python agent_relay.py relay-worker --source-worker <name> --target-worker <name>
```

## One-shot cycle

```powershell
python agent_relay.py run-cycle [--cwd <path>]
```

Runs: Claude task → relay output → Codex review. Stops after one review.

## State inspection

```powershell
python agent_relay.py status
```

## Configuration

```powershell
python agent_relay.py init-config          # write agents.example.json
python agent_relay.py report-template      # write report template
```
