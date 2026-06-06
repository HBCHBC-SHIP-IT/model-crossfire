# AgentRelay

AgentRelay is a file-queue workbench for multi-agent collaboration. A lead
model delegates scoped work to worker agents through file queues.

## Quick start

```bash
# Check environment
python agent_relay.py doctor

# Queue a task
python agent_relay.py queue <worker-name> --file <path-to-prompt.md> --role "<role description>"

# Run worker (Claude backend)
python agent_relay.py run-worker --worker <name> --backend claude --cwd <project-dir>

# Run worker (Codex backend)
python agent_relay.py run-worker --worker <name> --backend codex --cwd <project-dir>

# See state
python agent_relay.py status
```

## Worker behavior

When you receive a task through AgentRelay:

1. **Read the task envelope** — the Role section defines your scope.
2. **Stay in scope** — do not expand beyond what the role and task permit.
3. **Produce a Report** using this exact format:
   ```
   Report: <short title>
   Files changed: <list or - none>
   Tests: <results or - not run: reason>
   Result: PASS / BLOCKED / NEEDS_RETRY
   Risks: <list or - none>
   Next: <one recommended step>
   ```
4. **Be honest** — report exactly what you did and did not change.

## Safety

- Prefer read-only tasks.
- Never queue secrets, API keys, or credentials in task files.
- Worker output is not auto-accepted — a lead reviews it.
- Don't run concurrent workers that edit the same files.

## File layout

```
queue/to_<worker>/    ← task files land here
out/<worker>/         ← output reports appear here
logs/                 ← JSON run logs
locks/                ← prevents duplicate worker runs
```
