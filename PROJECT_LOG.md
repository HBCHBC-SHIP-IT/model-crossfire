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

## 2026-06-06 - AgentRelay Rename And Multi-Worker Foundation

- Renamed the public project identity from Model Crossfire to AgentRelay.
- Kept `model_crossfire.py` as a backward-compatible wrapper.
- Added `agent_relay.py` as the preferred entry point.
- Added arbitrary worker queues:
  - `queue/to_<worker>/`
  - `out/<worker>/`
- Added `run-worker` for named workers with `claude` or `codex` backends.
- Added `relay-worker` to review one worker's latest output with another worker.
- Added worker lock files under `locks/` to prevent accidental duplicate runs for the same worker.
- Added `status` to show pending tasks, outputs, and locks.
- Added task envelopes with role metadata and required report format.
- Added `agents.example.json` and `examples/report_template.md`.
- Preserved the original commands:
  - `run-claude`
  - `run-codex`
  - `relay-claude-to-codex`
  - `run-cycle`
- Intended open-source positioning:
  - A file-queue multi-agent workbench where a strong lead model delegates scoped work to worker models, then reviews durable reports.

## 2026-06-06 - AgentRelay Skill, Plugin, And Agent Integrations

- Created installable Codex skill at `skills/agent-relay/`:
  - `SKILL.md` with YAML frontmatter triggering on multi-agent collaboration,
    worker delegation, token reduction, and review flows.
  - `agents/openai.yaml` with scoped worker instructions and Report format.
  - `references/commands.md` for CLI command reference.
- Created Codex plugin bundle at `plugins/agent-relay/`:
  - Valid `.codex-plugin/plugin.json` manifest with a self-contained copy of
    the AgentRelay skill.
- Created repository marketplace metadata at
  `.agents/plugins/marketplace.json`.
- Added agent integrations:
  - `integrations/claude-code/CLAUDE.md` — explains how a Claude worker reads
    a queued task, follows report constraints, and avoids scope expansion.
  - `integrations/generic-agents/AGENTS.md` — concise fragment for agents
    without native Skill support.
- Updated root README with discovery and installation instructions.
- All existing CLI commands preserved; backward compatibility maintained.
- Validation:
  - `python -m py_compile agent_relay.py`: PASS.
  - `python -m py_compile model_crossfire.py`: PASS.
  - `python agent_relay.py doctor`: PASS.
  - `python agent_relay.py status`: PASS.
  - `git diff --check`: PASS.
  - Official `quick_validate.py` for both skill copies: PASS.
  - Official `validate_plugin.py`: PASS.
