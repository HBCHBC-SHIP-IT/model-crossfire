"""Model Crossfire: a file-queue bridge for Claude Code and Codex CLI.

The bridge avoids GUI automation. It sends prompts through files, runs one CLI
agent at a time, and stores durable outputs for review.
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
QUEUE_TO_CLAUDE = ROOT / "queue" / "to_claude"
QUEUE_TO_CODEX = ROOT / "queue" / "to_codex"
QUEUE_PROCESSED = ROOT / "queue" / "processed"
OUT_CLAUDE = ROOT / "out" / "claude"
OUT_CODEX = ROOT / "out" / "codex"
LOGS = ROOT / "logs"

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


def move_processed(task_path: Path, agent: str) -> Path:
    dest = QUEUE_PROCESSED / f"{task_path.stem}.{agent}.done.md"
    counter = 1
    while dest.exists():
        dest = QUEUE_PROCESSED / f"{task_path.stem}.{agent}.done.{counter}.md"
        counter += 1
    shutil.move(str(task_path), str(dest))
    return dest


def make_task(args: argparse.Namespace) -> int:
    queue = QUEUE_TO_CLAUDE if args.agent == "claude" else QUEUE_TO_CODEX
    source = Path(args.file)
    prompt = read_text(source)
    title = args.title or source.stem
    safe_title = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in title)
    task_path = queue / f"{now_stamp()}_{safe_title}.md"
    write_text(task_path, prompt)
    print(f"Task queued: {task_path}")
    return 0


def run_claude(args: argparse.Namespace) -> int:
    task = next_task(QUEUE_TO_CLAUDE)
    if task is None:
        print("No Claude task.")
        return 0

    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        print("Claude CLI not found on PATH.", file=sys.stderr)
        return 127

    prompt = read_text(task)
    out_path = OUT_CLAUDE / f"{task.stem}.claude.md"
    log_path = LOGS / f"{task.stem}.claude.json"

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
    if args.add_dir:
        cmd.extend(["--add-dir", args.add_dir])

    result = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=args.cwd or str(ROOT),
        timeout=args.timeout,
    )

    body = result.stdout or ""
    if result.stderr:
        body += "\n\n--- STDERR ---\n\n" + result.stderr
    write_text(out_path, body)
    write_json(
        log_path,
        {
            "agent": "claude",
            "task": str(task),
            "output": str(out_path),
            "returncode": result.returncode,
            "cmd": cmd,
            "cwd": args.cwd or str(ROOT),
        },
    )
    processed = move_processed(task, "claude")
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
    task = next_task(QUEUE_TO_CODEX)
    if task is None:
        print("No Codex task.")
        return 0

    codex_cmd = shutil.which("codex")
    if not codex_cmd:
        print("Codex CLI not found on PATH.", file=sys.stderr)
        return 127

    prompt = read_text(task)
    out_path = OUT_CODEX / f"{task.stem}.codex.md"
    log_path = LOGS / f"{task.stem}.codex.json"
    transcript_path = LOGS / f"{task.stem}.codex.stdout.txt"

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

    result = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=args.cwd or str(ROOT),
        timeout=args.timeout,
    )

    write_text(transcript_path, result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr)
    write_json(
        log_path,
        {
            "agent": "codex",
            "task": str(task),
            "output": str(out_path),
            "transcript": str(transcript_path),
            "returncode": result.returncode,
            "cmd": cmd,
            "cwd": args.cwd or str(ROOT),
        },
    )
    processed = move_processed(task, "codex")
    print(f"Codex output: {out_path}")
    print(f"Processed task: {processed}")
    return result.returncode


def relay_claude_to_codex(_: argparse.Namespace) -> int:
    outputs = sorted(OUT_CLAUDE.glob("*.md"))
    if not outputs:
        print("No Claude output to relay.")
        return 0
    latest = outputs[-1]
    content = read_text(latest)
    prompt = f"""Review this Claude output for the current project.

Do not implement unless explicitly instructed.
Check correctness, phase boundaries, tests, and privacy risks.
Flag mojibake or unclear output if present.

Claude output file:
{latest}

--- CLAUDE OUTPUT START ---
{content}
--- CLAUDE OUTPUT END ---
"""
    task_path = QUEUE_TO_CODEX / f"{now_stamp()}_review_{latest.stem}.md"
    write_text(task_path, prompt)
    print(f"Codex review task queued: {task_path}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Model Crossfire")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="Check CLI availability")
    p.set_defaults(func=doctor)

    p = sub.add_parser("queue", help="Queue a prompt file")
    p.add_argument("agent", choices=["claude", "codex"])
    p.add_argument("--file", required=True)
    p.add_argument("--title", default="")
    p.set_defaults(func=make_task)

    p = sub.add_parser("run-claude", help="Run one Claude queued task")
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
    p.set_defaults(func=run_claude)

    p = sub.add_parser("run-codex", help="Run one Codex queued task")
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
