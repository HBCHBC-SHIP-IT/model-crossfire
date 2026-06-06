# AgentRelay — Claude Code Worker Integration

When Claude Code is invoked as an AgentRelay worker, it receives a task file
from `queue/to_<worker>/`. The file follows the AgentRelay task envelope format
with YAML frontmatter and a structured body.

## How Claude reads a queued task

1. The task file is passed via `claude -p` with stdin containing the full
   envelope (frontmatter + body).
2. Claude sees the **Role** section defining its scope — this is the primary
   constraint.
3. Claude sees the **Required Output Format** section mandating the Report
   structure.
4. Claude processes the **Task** section as the prompt body.

## Report constraints

Every worker task MUST produce output matching:

```text
Report:
Files changed:
Tests:
Result:
Risks:
Next:
```

- **Report**: short path or title — one line
- **Files changed**: every file touched, or `- none`
- **Tests**: test results, or `- not run: <reason>`
- **Result**: exactly one of `PASS`, `BLOCKED`, or `NEEDS_RETRY`
- **Risks**: any risks found, or `- none`
- **Next**: one recommended next step

## Scope discipline

Claude as a worker MUST NOT expand scope:

- If the role says "read-only researcher", do not write code.
- If the role says "scoped implementer", only implement what the task
  explicitly requests.
- If the task says "do not run browser automation", do not use Playwright or
  browser tools.
- If the task says "do not start servers", do not launch dev servers.

The lead agent decides scope. The worker executes within it.

## Example: read-only worker

A task with `role: "read-only researcher"` should:

- Read project files, structure, and patterns
- Report findings in the Report format
- Never write, edit, or delete files
- Output `Files changed: - none`

The worker's value is in accurate, disciplined reporting — not in doing more
than asked.
