# Development workflow

`AGENTS.md` contains the repository rules. This document holds operational details so
routine tasks do not load a large checklist. `TASK_PROGRESS.txt` is the current checkpoint;
`docs/history/` preserves superseded checkpoints. Approved Superpowers specifications and
plans remain under `docs/superpowers/`.

## Codex and Superpowers configuration

The 2026-10-08 audit found no pre-existing repository/ancestor `AGENTS.md`, project Codex
configuration, or custom duplicate skills. The user configuration already selected
`gpt-6-astra`, but its default reasoning effort was `ultra`. The repository's
`.codex/config.toml` sets the requested Astra/Medium defaults without changing other
projects, permissions, sandbox, credentials, MCP servers, or installed plugins. An
explicit session override can take precedence; this does not change an already-running
chat's model or effort.

Superpowers remains installed. Its generic always-invoke/always-plan/worktree language
is narrowed by the user's selective workflow in `AGENTS.md`. Do not edit versioned plugin
cache files: updates would replace those edits and other projects would be affected.
There is no duplicate local skill collection to maintain. Read skills only for the part
of the current task they help, and retain their useful debugging and verification checks.

This follows the official guidance on [focused skills and repository instructions](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra),
[AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), and
[trusted project configuration](https://learn.chatgpt.com/docs/config-file/config-basic).

## Verification

Use focused tests during implementation. Run the applicable broader suites before
completion; documentation-only changes need link/config/diff checks, not another full
application test run. Record the command, result and scope in the current checkpoint.

Backend tests must run from a fresh temporary working directory, with the backend added
to `sys.path`, so imports cannot load the station's real `backend/.env`. For example,
from the repository root in PowerShell:

```powershell
@'
import os, sys, tempfile
from pathlib import Path
backend = Path('backend').resolve()
work = Path(tempfile.mkdtemp(prefix='bv-tests-'))
os.chdir(work)
sys.path.insert(0, str(backend))
import pytest
raise SystemExit(pytest.main([
    '-p', 'no:cacheprovider', '-q', '--basetemp', str(work / 'fixtures'),
    '-c', str(backend / 'pyproject.toml'), str(backend / 'tests'),
]))
'@ | & './backend/venv/Scripts/python.exe' -B -
```

For PostgreSQL-specific tests, explicitly set `BANANAVISION_TEST_DATABASE_URL` to a
disposable cluster before running that command. These tests create/drop unique schemas.
Never use the station URL. Record the disposable cluster directory/port while it exists,
then stop that exact instance and remove its generated files after verification. Tests
without an isolated PostgreSQL URL skip those cases; report that limitation.

Run the configured backend lint with `ruff check backend/app backend/tests`. Use a
temporary tool environment if Ruff is unavailable; do not silently modify production
dependencies. Never run broad autofixes solely to hide baseline lint failures.

From `frontend/`:

```powershell
node --test --test-concurrency=1 tests/*.test.mjs
npm run typecheck
npm run build
npm run lint
```

The browser tests use Vite and mocked API fixtures. Set `PLAYWRIGHT_MODULE` to an installed
Playwright module if the test harness cannot resolve it; keep machine-specific paths out
of versioned configuration. The production build includes the referenced TypeScript
projects (`tsc -b`). Treat known existing lint debt separately from newly added diagnostics.

Finish by reviewing `git diff --check`, changed paths and the actual diff. Do not restore
reverted Scan Logs/Scan Detail changes as incidental cleanup.
