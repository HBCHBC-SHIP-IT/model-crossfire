"""AgentRelay: a file-queue bridge for multi-agent CLI collaboration.

The bridge avoids GUI automation. It sends prompts through files, runs CLI
agents as workers, and stores durable outputs for lead-agent review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUEUE_ROOT = ROOT / "queue"
QUEUE_TO_CLAUDE = QUEUE_ROOT / "to_claude"
QUEUE_TO_CODEX = QUEUE_ROOT / "to_codex"
QUEUE_PROCESSED = ROOT / "queue" / "processed"
OUT_ROOT = ROOT / "out"
OUT_CLAUDE = OUT_ROOT / "claude"
OUT_CODEX = OUT_ROOT / "codex"
LOGS = ROOT / "logs"
LOCKS = ROOT / "locks"
CONFIG_EXAMPLE = ROOT / "agents.example.json"

MOJIBAKE_REPLACEMENTS = {
    "鈥檚": "'s",
    "鈥檛": "n't",
    "鈥?": "-",
    "鈫?": "->",
    "鈥�": "-",
    "閳": "",
}


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    for path in [
        QUEUE_TO_CLAUDE,
        QUEUE_TO_CODEX,
        QUEUE_PROCESSED,
        OUT_CLAUDE,
        OUT_CODEX,
        LOGS,
        LOCKS,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def sanitize_text(text: str) -> str:
    """Remove common mojibake seen when CLI output crosses Windows shells."""
    cleaned = text
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    return cleaned


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sanitize_text(text), encoding="utf-8")


def next_task(queue_dir: Path) -> Path | None:
    tasks = sorted(queue_dir.glob("*.md"))
    return tasks[0] if tasks else None


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def queue_for_worker(worker: str) -> Path:
    return QUEUE_ROOT / f"to_{safe_name(worker)}"


def out_for_worker(worker: str) -> Path:
    return OUT_ROOT / safe_name(worker)


def acquire_lock(worker: str) -> Path:
    lock_path = LOCKS / f"{safe_name(worker)}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock_path.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "worker": worker,
                        "created_at": dt.datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    except FileExistsError as exc:
        raise RuntimeError(
            f"Worker {worker!r} already has a lock: {lock_path}"
        ) from exc
    return lock_path


def release_lock(lock_path: Path | None) -> None:
    if lock_path and lock_path.exists():
        lock_path.unlink()


def move_processed(task_path: Path, agent: str) -> Path:
    dest = QUEUE_PROCESSED / f"{task_path.stem}.{agent}.done.md"
    counter = 1
    while dest.exists():
        dest = QUEUE_PROCESSED / f"{task_path.stem}.{agent}.done.{counter}.md"
        counter += 1
    shutil.move(str(task_path), str(dest))
    return dest


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def write_run_started(
    *,
    log_path: Path,
    agent: str,
    worker: str,
    task: Path,
    output: Path,
    cmd: list[str],
    cwd: str,
    timeout: int,
) -> str:
    started_at = dt.datetime.now().isoformat()
    write_json(
        log_path,
        {
            "agent": agent,
            "worker": worker,
            "task": str(task),
            "output": str(output),
            "status": "running",
            "started_at": started_at,
            "timeout_seconds": timeout,
            "cmd": cmd,
            "cwd": cwd,
        },
    )
    return started_at


def write_timeout_report(
    *,
    exc: subprocess.TimeoutExpired,
    out_path: Path,
    log_path: Path,
    agent: str,
    worker: str,
    task: Path,
    cmd: list[str],
    cwd: str,
    started_at: str,
) -> Path:
    ended_at = dt.datetime.now().isoformat()
    stdout = decode_timeout_output(exc.stdout)
    stderr = decode_timeout_output(exc.stderr)
    body = (
        f"# AgentRelay timeout\n\n"
        f"Agent `{agent}` worker `{worker}` exceeded the configured "
        f"timeout of {exc.timeout} seconds.\n\n"
        "The child process was terminated before a complete response was "
        "returned. Any token usage that happened before timeout may still "
        "be billed by the provider.\n\n"
        f"- Task: `{task}`\n"
        f"- Started at: `{started_at}`\n"
        f"- Ended at: `{ended_at}`\n"
        f"- CWD: `{cwd}`\n\n"
    )
    if stdout:
        body += "## Partial stdout\n\n```text\n" + stdout + "\n```\n\n"
    if stderr:
        body += "## Partial stderr\n\n```text\n" + stderr + "\n```\n\n"
    if not stdout and not stderr:
        body += "No partial stdout/stderr was captured before timeout.\n"
    write_text(out_path, body)
    write_json(
        log_path,
        {
            "agent": agent,
            "worker": worker,
            "task": str(task),
            "output": str(out_path),
            "status": "timeout",
            "started_at": started_at,
            "ended_at": ended_at,
            "timeout_seconds": exc.timeout,
            "returncode": 124,
            "cmd": cmd,
            "cwd": cwd,
        },
    )
    return move_processed(task, worker)


def terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()


def run_agent_command(
    *,
    cmd: list[str],
    prompt: str,
    cwd: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )
    try:
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process_tree(proc)
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output=stdout,
            stderr=stderr,
        ) from None
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def make_task(args: argparse.Namespace) -> int:
    queue = queue_for_worker(args.agent)
    source = Path(args.file)
    prompt = read_text(source)
    title = args.title or source.stem
    safe_title = safe_name(title)
    task_path = queue / f"{now_stamp()}_{safe_title}.md"
    if args.raw:
        body = prompt
    else:
        body = build_task_envelope(
            title=title,
            worker=args.agent,
            role=args.role,
            prompt=prompt,
        )
    write_text(task_path, body)
    print(f"Task queued: {task_path}")
    return 0


def build_task_envelope(
    *,
    title: str,
    worker: str,
    role: str,
    prompt: str,
) -> str:
    return f"""---
title: {title}
worker: {worker}
role: {role}
created_at: {dt.datetime.now().isoformat()}
report_required: true
---

# AgentRelay Task

## Role

{role}

## Required Output Format

Use this structure in your final report:

```text
Report:
Files changed:
Tests:
Result:
Risks:
Next:
```

## Task

{prompt}
"""


def run_claude(args: argparse.Namespace) -> int:
    worker = getattr(args, "worker", "claude")
    task = next_task(queue_for_worker(worker))
    if task is None:
        print(f"No task for worker {worker}.")
        return 0

    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        print("Claude CLI not found on PATH.", file=sys.stderr)
        return 127

    prompt = read_text(task)
    out_path = out_for_worker(worker) / f"{task.stem}.{worker}.md"
    log_path = LOGS / f"{task.stem}.{worker}.json"

    cmd = [
        claude_cmd,
        "-p",
        "--output-format",
        "text",
        "--permission-mode",
        args.permission_mode,
    ]
    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if getattr(args, "strict_empty_mcp", False):
        empty_mcp = ROOT / "empty-mcp.json"
        if not empty_mcp.exists():
            empty_mcp.write_text('{\n  "mcpServers": {}\n}\n', encoding="utf-8")
        cmd.extend(["--strict-mcp-config", "--mcp-config", str(empty_mcp)])
    if args.add_dir:
        cmd.extend(["--add-dir", args.add_dir])

    cwd = args.cwd or str(ROOT)
    lock_path = acquire_lock(worker)
    started_at = write_run_started(
        log_path=log_path,
        agent="claude",
        worker=worker,
        task=task,
        output=out_path,
        cmd=cmd,
        cwd=cwd,
        timeout=args.timeout,
    )
    try:
        result = run_agent_command(
            cmd=cmd,
            prompt=prompt,
            cwd=cwd,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as exc:
        processed = write_timeout_report(
            exc=exc,
            out_path=out_path,
            log_path=log_path,
            agent="claude",
            worker=worker,
            task=task,
            cmd=cmd,
            cwd=cwd,
            started_at=started_at,
        )
        print(f"Claude timed out: {out_path}", file=sys.stderr)
        print(f"Processed task: {processed}", file=sys.stderr)
        return 124
    finally:
        release_lock(lock_path)

    body = result.stdout or ""
    if result.stderr:
        body += "\n\n--- STDERR ---\n\n" + result.stderr
    write_text(out_path, body)
    write_json(
        log_path,
        {
            "agent": "claude",
            "worker": worker,
            "task": str(task),
            "output": str(out_path),
            "status": "completed",
            "started_at": started_at,
            "ended_at": dt.datetime.now().isoformat(),
            "returncode": result.returncode,
            "cmd": cmd,
            "cwd": cwd,
        },
    )
    processed = move_processed(task, worker)
    print(f"Claude output: {out_path}")
    print(f"Processed task: {processed}")
    return result.returncode


def run_cycle(args: argparse.Namespace) -> int:
    """Run one Claude task, relay its output, then run one Codex review."""
    claude_args = argparse.Namespace(
        cwd=args.cwd,
        add_dir=args.add_dir,
        timeout=args.claude_timeout,
        permission_mode=args.claude_permission_mode,
        dangerously_skip_permissions=args.claude_dangerously_skip_permissions,
        strict_empty_mcp=args.claude_strict_empty_mcp,
    )
    claude_code = run_claude(claude_args)
    if claude_code != 0 and not args.relay_on_claude_failure:
        print(
            "Claude returned non-zero; not relaying to Codex. "
            "Use --relay-on-claude-failure to review failed outputs."
        )
        return claude_code

    relay_code = relay_claude_to_codex(argparse.Namespace())
    if relay_code != 0:
        return relay_code

    codex_args = argparse.Namespace(
        cwd=args.cwd,
        timeout=args.codex_timeout,
        sandbox=args.codex_sandbox,
    )
    return run_codex(codex_args)


def run_codex(args: argparse.Namespace) -> int:
    worker = getattr(args, "worker", "codex")
    task = next_task(queue_for_worker(worker))
    if task is None:
        print(f"No task for worker {worker}.")
        return 0

    codex_cmd = shutil.which("codex")
    if not codex_cmd:
        print("Codex CLI not found on PATH.", file=sys.stderr)
        return 127

    prompt = read_text(task)
    out_path = out_for_worker(worker) / f"{task.stem}.{worker}.md"
    log_path = LOGS / f"{task.stem}.{worker}.json"
    transcript_path = LOGS / f"{task.stem}.{worker}.stdout.txt"

    cmd = [
        codex_cmd,
        "exec",
        "-C",
        args.cwd or str(ROOT),
        "-s",
        args.sandbox,
        "--skip-git-repo-check",
        "-o",
        str(out_path),
        "-",
    ]

    cwd = args.cwd or str(ROOT)
    lock_path = acquire_lock(worker)
    started_at = write_run_started(
        log_path=log_path,
        agent="codex",
        worker=worker,
        task=task,
        output=out_path,
        cmd=cmd,
        cwd=cwd,
        timeout=args.timeout,
    )
    try:
        result = run_agent_command(
            cmd=cmd,
            prompt=prompt,
            cwd=cwd,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as exc:
        processed = write_timeout_report(
            exc=exc,
            out_path=out_path,
            log_path=log_path,
            agent="codex",
            worker=worker,
            task=task,
            cmd=cmd,
            cwd=cwd,
            started_at=started_at,
        )
        print(f"Codex timed out: {out_path}", file=sys.stderr)
        print(f"Processed task: {processed}", file=sys.stderr)
        return 124
    finally:
        release_lock(lock_path)

    write_text(transcript_path, result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr)
    write_json(
        log_path,
        {
            "agent": "codex",
            "worker": worker,
            "task": str(task),
            "output": str(out_path),
            "transcript": str(transcript_path),
            "status": "completed",
            "started_at": started_at,
            "ended_at": dt.datetime.now().isoformat(),
            "returncode": result.returncode,
            "cmd": cmd,
            "cwd": cwd,
        },
    )
    processed = move_processed(task, worker)
    print(f"Codex output: {out_path}")
    print(f"Processed task: {processed}")
    return result.returncode


def relay_claude_to_codex(_: argparse.Namespace) -> int:
    return relay_worker_output(
        argparse.Namespace(source_worker="claude", target_worker="codex")
    )


def relay_worker_output(args: argparse.Namespace) -> int:
    source_worker = args.source_worker
    target_worker = args.target_worker
    outputs = sorted(out_for_worker(source_worker).glob("*.md"))
    if not outputs:
        print(f"No output to relay from worker {source_worker}.")
        return 0
    latest = outputs[-1]
    content = read_text(latest)
    prompt = f"""Review this worker output for the current project.

Do not implement unless explicitly instructed.
Check correctness, phase boundaries, tests, and privacy risks.
Flag mojibake or unclear output if present.

Worker:
{source_worker}

Output file:
{latest}

--- WORKER OUTPUT START ---
{content}
--- WORKER OUTPUT END ---
"""
    task_path = queue_for_worker(target_worker) / f"{now_stamp()}_review_{latest.stem}.md"
    write_text(task_path, prompt)
    print(f"Review task queued for {target_worker}: {task_path}")
    return 0


def write_json(path: Path, data: dict) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def doctor(_: argparse.Namespace) -> int:
    ensure_dirs()
    for name in ["claude", "codex"]:
        found = shutil.which(name)
        print(f"{name}: {found or 'NOT FOUND'}")
    print(f"root: {ROOT}")
    return 0


def status(_: argparse.Namespace) -> int:
    ensure_dirs()
    workers = set()
    for path in QUEUE_ROOT.glob("to_*"):
        if path.is_dir():
            workers.add(path.name.removeprefix("to_"))
    for path in OUT_ROOT.glob("*"):
        if path.is_dir():
            workers.add(path.name)

    if not workers:
        print("No workers found.")
        return 0

    print("Worker status:")
    for worker in sorted(workers):
        pending = len(list(queue_for_worker(worker).glob("*.md")))
        outputs = len(list(out_for_worker(worker).glob("*.md")))
        locked = (LOCKS / f"{safe_name(worker)}.lock").exists()
        print(
            f"- {worker}: pending={pending} outputs={outputs} "
            f"locked={'yes' if locked else 'no'}"
        )
    return 0


def write_report_template(args: argparse.Namespace) -> int:
    dest = Path(args.output)
    template = """# AgentRelay Worker Report

## Report

<short path or title>

## Files Changed

- none

## Tests

- not run: <reason>

## Result

PASS / BLOCKED / NEEDS_RETRY

## Risks

- <risk or none>

## Next

- <one recommended next step>
"""
    write_text(dest, template)
    print(f"Report template written: {dest}")
    return 0


def init_config(_: argparse.Namespace) -> int:
    if CONFIG_EXAMPLE.exists():
        print(f"Config example already exists: {CONFIG_EXAMPLE}")
        return 0
    config = {
        "lead": {
            "worker": "codex",
            "backend": "codex",
            "role": "technical lead and reviewer",
        },
        "workers": [
            {
                "worker": "claude-research",
                "backend": "claude",
                "role": "read-only researcher",
                "writes": "reports only",
            },
            {
                "worker": "claude-impl",
                "backend": "claude",
                "role": "scoped implementer",
                "writes": "code only when explicitly allowed",
            },
        ],
    }
    write_json(CONFIG_EXAMPLE, config)
    print(f"Config example written: {CONFIG_EXAMPLE}")
    return 0


def run_worker(args: argparse.Namespace) -> int:
    if args.backend == "claude":
        return run_claude(args)
    if args.backend == "codex":
        return run_codex(args)
    print(f"Unsupported backend: {args.backend}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentRelay")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="Check CLI availability")
    p.set_defaults(func=doctor)

    p = sub.add_parser("status", help="Show queued tasks, outputs, and locks")
    p.set_defaults(func=status)

    p = sub.add_parser("init-config", help="Write agents.example.json")
    p.set_defaults(func=init_config)

    p = sub.add_parser("report-template", help="Write a worker report template")
    p.add_argument("--output", default=str(ROOT / "examples" / "report_template.md"))
    p.set_defaults(func=write_report_template)

    p = sub.add_parser("queue", help="Queue a prompt file")
    p.add_argument("agent")
    p.add_argument("--file", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--role", default="scoped worker")
    p.add_argument(
        "--raw",
        action="store_true",
        help="Queue the prompt exactly as written, without AgentRelay metadata.",
    )
    p.set_defaults(func=make_task)

    p = sub.add_parser("run-worker", help="Run one queued task for a named worker")
    p.add_argument("--worker", required=True)
    p.add_argument("--backend", required=True, choices=["claude", "codex"])
    p.add_argument("--cwd", default="")
    p.add_argument("--add-dir", default="")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--sandbox", default="workspace-write")
    p.add_argument(
        "--permission-mode",
        default="default",
        choices=[
            "default",
            "acceptEdits",
            "auto",
            "bypassPermissions",
            "dontAsk",
            "plan",
        ],
    )
    p.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Pass Claude's permission bypass flag. Use only in trusted workspaces.",
    )
    p.add_argument(
        "--strict-empty-mcp",
        action="store_true",
        help="Run Claude with an empty MCP config to avoid user/project MCP startup hangs.",
    )
    p.set_defaults(func=run_worker)

    p = sub.add_parser("run-claude", help="Run one Claude queued task")
    p.add_argument("--worker", default="claude")
    p.add_argument("--cwd", default="")
    p.add_argument("--add-dir", default="")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument(
        "--permission-mode",
        default="default",
        choices=[
            "default",
            "acceptEdits",
            "auto",
            "bypassPermissions",
            "dontAsk",
            "plan",
        ],
    )
    p.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Pass Claude's permission bypass flag. Use only in trusted workspaces.",
    )
    p.add_argument(
        "--strict-empty-mcp",
        action="store_true",
        help="Run Claude with an empty MCP config to avoid user/project MCP startup hangs.",
    )
    p.set_defaults(func=run_claude)

    p = sub.add_parser("run-codex", help="Run one Codex queued task")
    p.add_argument("--worker", default="codex")
    p.add_argument("--cwd", default="")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--sandbox", default="workspace-write")
    p.set_defaults(func=run_codex)

    p = sub.add_parser(
        "relay-claude-to-codex",
        help="Queue latest Claude output for Codex review",
    )
    p.set_defaults(func=relay_claude_to_codex)

    p = sub.add_parser(
        "relay-worker",
        help="Queue latest output from one worker for another worker to review",
    )
    p.add_argument("--source-worker", required=True)
    p.add_argument("--target-worker", default="codex")
    p.set_defaults(func=relay_worker_output)

    p = sub.add_parser(
        "run-cycle",
        help="Run one Claude task, relay output, then run one Codex review",
    )
    p.add_argument("--cwd", default="")
    p.add_argument("--add-dir", default="")
    p.add_argument("--claude-timeout", type=int, default=1800)
    p.add_argument("--codex-timeout", type=int, default=1800)
    p.add_argument("--codex-sandbox", default="workspace-write")
    p.add_argument(
        "--claude-permission-mode",
        default="bypassPermissions",
        choices=[
            "default",
            "acceptEdits",
            "auto",
            "bypassPermissions",
            "dontAsk",
            "plan",
        ],
    )
    p.add_argument(
        "--claude-dangerously-skip-permissions",
        action="store_true",
        help="Pass Claude's permission bypass flag. Use only in trusted workspaces.",
    )
    p.add_argument(
        "--claude-strict-empty-mcp",
        action="store_true",
        help="Run Claude with an empty MCP config to avoid user/project MCP startup hangs.",
    )
    p.add_argument(
        "--relay-on-claude-failure",
        action="store_true",
        help="Still queue Claude output for Codex review when Claude exits non-zero.",
    )
    p.set_defaults(func=run_cycle)

    return parser


def main(argv: list[str]) -> int:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
