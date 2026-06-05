# PROJECT_LOG.md

## 2026-06-06 - Initial Prototype And GitHub Publish

- Project name: Model Crossfire.
- Purpose: file-queue bridge for Claude Code and Codex CLI collaboration.
- Collaboration model:
  - lead agent creates scoped task files;
  - Claude Code executes one queued task;
  - Claude output is written to `out/claude/`;
  - latest Claude output can be relayed to Codex;
  - Codex reviews one queued task and writes to `out/codex/`.
- Validation:
  - `python -m py_compile model_crossfire.py`: PASS.
  - `python model_crossfire.py doctor`: PASS.
  - Local read-only project status check through Claude CLI: PASS in the POC directory.
  - Relay latest Claude output to Codex review task: PASS in the POC directory.
  - Codex CLI review run: PASS in the POC directory.
- Important fixes discovered during POC:
  - Windows needs `shutil.which()` to resolve `claude.cmd` and `codex.cmd`.
  - CLI output must force UTF-8 with replacement to avoid Windows GBK decode crashes.
  - `codex exec` options must precede the `-` stdin prompt marker.
  - This Codex CLI version does not support `-a/--ask-for-approval` under `codex exec`.
- Privacy:
  - Public repo excludes generated queues, outputs, logs, credentials, local project paths, and private project data.
- Published repository:
  - https://github.com/HBCHBC-SHIP-IT/model-crossfire

## Current Limitations

- One-shot queue processing only; no infinite autonomous loop.
- Codex Desktop GUI is not driven directly.
- Claude/Codex CLI authentication must already work locally.
- Queue/output files are plain text and should not contain secrets.

## 2026-06-06 - Crossfire Cycle Command

- Added `run-cycle` to process one Claude task, relay the latest Claude output to Codex, run one Codex review, then stop.
- Added Claude permission bypass support:
  - `--permission-mode bypassPermissions`
  - `--dangerously-skip-permissions`
- This maps to the user's Claude UI auto-approval workflow without requiring GUI key presses such as Shift+Tab.
- The tool still does not drive the Claude/Codex desktop windows; it uses CLI processes and file outputs.
- This preserves the human gate between cycles and avoids uncontrolled infinite agent loops.
