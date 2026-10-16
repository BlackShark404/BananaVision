# BananaVision repository guidance

- When resuming work, read `TASK_PROGRESS.txt` and the current Git status first. Use its latest resume point; historical checkpoints are reference material, not pending work.
- Trace the affected API, service, schema and UI before editing. Preserve explicit reverts, unrelated user changes, existing architecture and working behavior.
- Preserve the existing UI layout, components, styling, spacing and typography unless the user requests a redesign. Keep frontend/backend field names and types synchronized.
- Keep business timestamps and date boundaries consistent with the backend Asia/Manila helpers. Reuse existing conversions rather than adding competing timezone logic.
- Never test against the live station database, captures, physical cameras or OS power. Use isolated fixtures and disposable PostgreSQL schemas; inspect test setup first.
- Destructive live operations, deployment, history rewrites and shared-branch writes need explicit authorization. Do not read or print secrets to diagnose configuration.
- Run targeted regressions while implementing. Before completion, run relevant backend and frontend tests, type checks, configured lint and build, then review the scoped diff.
- Report exact results and distinguish existing lint debt from new regressions. Repeat passing checks only when changes or new evidence justify it.
- Work on the existing `main` branch exclusively. Do not create or switch to other branches or Git worktrees unless explicitly requested.
- Never automatically stage, commit, push, deploy, or discard changes without explicit authorization.
- Keep configuration changes minimal, reversible, and compatible with the existing development environment.

## Selective Superpowers workflow

These are the user's repository-specific choices for applying generic skill workflows:

- Use systematic debugging for unexpected behavior; TDD/regression tests when they can prove a behavioral fix; concise planning for substantial or architectural work.
- Reuse approved specs and plans. Continue authorized implementation without duplicate brainstorming or stage approvals; clarify only genuinely unresolved decisions.
- Review security-sensitive authorization, persistence, archive/file and maintenance boundaries. Use Context7 or primary documentation when library behavior is uncertain.
- Prefer the current checkout. Worktrees require explicit authorization and a genuine isolation need; subagents are for useful independent work or a focused final review, not an automatic per-step ritual.
- Load relevant skills/references on demand. Do not run a full skill chain for small edits or copy vendor skill instructions into additional local skills.
- Default to GPT-6 Astra Medium; use High when hard concurrency, recovery or architecture reasoning warrants it, where the model selection is available. Follow explicit task/model overrides.
- Keep `TASK_PROGRESS.txt` limited to current milestones, pending work, verified results, constraints and an exact next step. Archive superseded content before replacing it.

Read [the development workflow](docs/development-workflow.md) for verification commands and tooling details.

For maintenance changes, use the approved [design](docs/superpowers/specs/2026-10-05-system-maintenance-design.md) and [plan](docs/superpowers/plans/2026-10-06-system-maintenance.md).

Consult [backend documentation](backend/README.md) for deployment/migrations; do not load every document for unrelated changes.

## Automatic AI knowledge management

This repository uses three complementary tools:

- **Graphify:** Source-code knowledge graph, architecture and dependency relationships.
- **Obsidian:** Human-readable project documentation and linked Markdown notes.
- **ICM:** Persistent project memory shared across compatible AI coding assistants.

Use these tools automatically when relevant. The user must not need to explicitly request Graphify, Obsidian or ICM during ordinary development.

Apply the following principles:

- Select tools based on task complexity and relevance rather than running all three unconditionally.
- Reuse existing knowledge before repeating expensive analysis.
- Prefer targeted queries and minimal relevant context to reduce token consumption.
- Keep persistent knowledge synchronized with verified implementation changes.
- Never assume stored memories or documentation are more authoritative than the current source code.
- Preserve existing integrations, skills, MCP connections, and repository configurations.
- Do not install duplicate tools, create unnecessary background services, or repeatedly initialize existing integrations.
- If a tool is unavailable, continue using available evidence when safe and report the limitation without pretending the tool succeeded.

Detailed conditional knowledge-management procedures may be stored in `.agents/rules/ai-knowledge-lifecycle.md`. Do not duplicate lengthy instructions across multiple files.

## Graphify — Codebase intelligence

This project has a knowledge graph at `graphify-out/` with code nodes, community structure, and cross-file relationships.

Graphify is the primary tool for understanding existing code relationships before nontrivial implementation changes.

When the user types `/graphify`, use the installed Graphify skill or instructions before doing anything else.

### Rules

- When `graphify-out/graph.json` exists, run `graphify query "<question>"` before the first broad grep, search or source-file exploration for nontrivial codebase questions, and include this rule in subagent prompts that explore code.
- For trivial, explicitly scoped edits, unnecessary graph queries may be skipped when the affected source location is already known.
- Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts.
- These commands return scoped subgraphs, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- Read raw files to inspect and verify the source locations identified by the graph or earlier relevant reads. Expand the search if graph coverage is incomplete, stale or incorrect.
- Dirty `graphify-out/` files are expected after hooks or incremental updates; dirty graph files are not a reason to skip Graphify.
- Skip Graphify when the user explicitly prohibits it, when the task concerns incorrect graph output itself, or when graph analysis would add no useful information.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of unnecessary raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not provide enough context.
- After modifying relevant code, run `graphify update .` to keep the graph current using the existing local AST workflow.
- When an existing hook has already performed a successful update, do not repeat it unnecessarily.
- Update the graph once after a coherent change set rather than after every individual file edit.
- Verify that the update succeeded. If unexpected large-scale graph loss occurs, investigate before accepting or committing the generated output.
- A committed `graphify-out/graph.json` is rewritten whole on every build, so a large diff may be expected. Do not automatically classify it as unnecessary churn or skip a required graph update.
- Never activate paid semantic extraction, upload private project files, or require external API credentials without authorization.
- Preserve the installed Graphify skill and its existing supported integrations.

## Obsidian — Project documentation

The project knowledge base is an Obsidian vault located at:

`docs/knowledge/`

The vault consists of ordinary Markdown files that can be read and updated directly by the AI coding assistant.

An Obsidian MCP connection is not required for basic local documentation access.

### Automatic documentation workflow

- Read relevant Obsidian notes when investigating architecture, implementation history, database design, APIs, models, testing or documented decisions.
- Do not read the entire vault for every task. Load only relevant notes.
- Verify technical statements against the current codebase before relying on them.
- After meaningful, successfully verified changes, automatically create or update the affected documentation when appropriate.
- Document significant API contract changes, database schema changes, model integration changes, architectural decisions, confirmed bug resolutions and relevant testing procedures.
- Prefer updating existing notes over creating redundant documentation.
- Preserve existing note names, manually written content, formatting and Obsidian `[[internal links]]`.
- Add internal links between genuinely related notes when useful.
- Keep documentation concise, structured and easy to navigate.
- Do not paste large source files, entire terminal outputs, or complete conversation transcripts into notes.
- Do not create documentation for every minor UI edit, routine formatting change or temporary investigation.
- Do not invent implementation details, test results or architectural decisions.
- Never store API keys, passwords, authentication tokens, private credentials or sensitive database contents.
- Treat source code as authoritative when documentation and implementation disagree. Report significant discrepancies and update documentation only when the correct behavior is established.
- Keep useful project Markdown documentation suitable for version control while excluding local Obsidian settings when appropriate.

### Documentation synchronization

After a significant verified development change:

1. Determine whether existing documentation is affected.
2. Locate the most relevant Obsidian note.
3. Update only the sections affected by the implementation.
4. Preserve links and unrelated user-authored content.
5. Verify the documentation against the final source code.
6. Report the documentation changes in the task summary.

Documentation updates should happen automatically when justified, without requiring another user prompt.

## ICM — Persistent AI memory

ICM provides project-specific persistent memory for development decisions, verified solutions, conventions and reusable knowledge.

The project memory database is:

`.icm/memories.db`

Use the existing ICM MCP tools and project-local configuration. Do not silently switch to the global memory database.

### Automatic memory recall

- Before substantial development tasks, recall relevant existing memories when previous decisions or solutions could materially affect implementation.
- Prefer focused recall queries instead of retrieving all stored memories.
- Use remembered decisions to avoid repeating resolved discussions, introducing previously rejected approaches or reintroducing known defects.
- Check whether a stored decision has been superseded by the current code, documentation or user instructions.
- Current explicit user instructions and verified repository state take precedence over old memories.
- Avoid repeated recall of the same information during one task unless necessary.
- Do not make unnecessary memory calls for trivial, unrelated changes.

### Automatic memory storage

After a meaningful development task is successfully verified, evaluate whether its outcome is worth remembering.

Store concise memories for:

- Important architectural decisions.
- Confirmed bug root causes and successfully tested fixes.
- Reusable implementation patterns.
- Established project conventions.
- Significant compatibility findings.
- Security-sensitive implementation lessons without secrets.
- Important technical constraints that affect future development.

Before storing:

1. Confirm the information is accurate.
2. Check whether similar information already exists.
3. Avoid creating duplicate memories.
4. Prefer a concise summary with useful keywords.
5. Associate the memory with a relevant BananaVision project topic.
6. Store only information likely to be useful in future sessions.

Never store:

- Unverified assumptions or speculative diagnoses.
- Failed experiments represented as successful solutions.
- Passwords, credentials or sensitive user information.
- Large logs, entire source files or complete conversation transcripts.
- Temporary debugging details without lasting value.
- Routine progress already maintained in `TASK_PROGRESS.txt`.

Do not automatically delete, prune, consolidate or overwrite existing memories without appropriate review and authorization.

Do not enable indiscriminate automatic capture of every tool call or terminal output.

### Cross-assistant consistency

- Codex and Antigravity should use the same BananaVision project memory database when their ICM MCP connections are available.
- Project memories must remain separate from unrelated repositories.
- Do not assume that a successful MCP connection guarantees every stored fact is accurate.
- When memory conflicts with verified source code or a newer explicit decision, resolve the discrepancy before storing a replacement.
- Preserve the existing ICM configuration and avoid unnecessary reinitialization.

## Automatic development lifecycle

Follow this workflow during normal BananaVision development without requiring the user to mention the three knowledge tools.

### Before implementation

1. Read `TASK_PROGRESS.txt` and inspect the current Git status.
2. Identify the latest authorized resume point, relevant requirements and affected system components.
3. Recall relevant ICM memories when previous decisions or confirmed solutions matter.
4. Query the existing Graphify graph when code architecture, dependencies or data flow must be understood.
5. Read relevant Obsidian notes when documentation provides necessary context.
6. Inspect the actual source code and verify assumptions.
7. Select an appropriately scoped implementation and testing approach.

### During implementation

1. Follow the existing BananaVision architecture and repository constraints.
2. Preserve explicit user reverts, unrelated modifications and working behavior.
3. Make necessary changes to authorized frontend, backend, database, configuration, test and documentation files.
4. Use Superpowers, Context7, Graphify and other available skills selectively when relevant.
5. Avoid redundant tool calls and unnecessary reanalysis.
6. Run targeted tests while implementing meaningful behavior changes.
7. Keep frontend/backend contracts and Asia/Manila timestamp handling consistent.
8. Never perform destructive operations, deployment or unauthorized Git writes.
9. Keep working context focused on the current task.

### After implementation

1. Run the required relevant tests, type checks, lint and build.
2. Investigate and report failures without misrepresenting the verification status.
3. Refresh Graphify when relevant code changes require it, unless a verified hook has already updated the graph.
4. Update affected Obsidian documentation when significant implementation details have changed.
5. Store important confirmed decisions or reusable fixes in ICM when beneficial.
6. Update `TASK_PROGRESS.txt` when task progress, milestones, pending work or the exact resume point have changed.
7. Review the scoped Git diff for unintended modifications.
8. Summarize application changes, knowledge updates, tests performed, unresolved issues and the next step when applicable.

Do not claim a task is fully complete if essential tests have failed or were not performed.

## Tool efficiency and token management

Choose the smallest useful knowledge workflow.

- **Trivial text or style edit:** Inspect the affected component, make the edit and verify it. Skip unrelated Graphify, Obsidian and ICM operations.
- **Nontrivial bug fix:** Use focused Graphify investigation and relevant ICM recall. Update Obsidian or ICM afterward only if the verified fix creates reusable knowledge.
- **Architectural change:** Consult relevant graph relationships, documentation and past decisions. Synchronize the affected knowledge sources after successful verification.
- **Database or API change:** Trace dependencies, verify contracts and update affected technical documentation.
- **Documentation-only task:** Work primarily with Obsidian Markdown files and verify relevant source details. Do not unnecessarily rebuild the graph.
- **Repeated problem:** Recall applicable ICM findings before repeating a broad investigation, then validate against current code.
- **Research or explanation:** Use relevant existing documentation and targeted analysis without modifying persistent knowledge unless requested.
- **Subagent delegation:** Provide only the relevant constraints, source references and knowledge context needed for the delegated work.

Do not invoke all three tools merely to satisfy a checklist.

Avoid unnecessary full-graph scans, repeated memory retrieval, duplicate documentation updates and redundant test execution.

Use expensive reasoning, multi-agent work and additional tool calls only when task complexity justifies them.

## Configuration and integration protection

- Preserve working Graphify, Obsidian and ICM integrations.
- Use existing installed skills and MCP servers rather than installing duplicates.
- Verify external tool capabilities before changing configuration.
- Keep detailed optional procedures in supported project-scoped rules or skills when appropriate.
- Do not duplicate large instruction blocks across `AGENTS.md`, `.agents/rules/` and tool-specific skill files.
- Review existing hooks before adding new hooks.
- Prefer conditional agent instructions over automatic hooks that run expensive operations after every edit.
- Do not enable background memory collection, paid AI extraction or external synchronization without authorization.
- Keep private memory databases, machine-specific settings and secrets out of version control.
- Do not reset or recreate existing graph or memory data unless necessary and approved.
- Document important integration changes and verify them before declaring success.

## Source-of-truth precedence

When information conflicts, use this order:

1. Current explicit user instructions and authorized task requirements.
2. Verified implementation and observed test results.
3. Approved specifications and current project documentation.
4. Relevant repository guidance and established project conventions.
5. Existing ICM memories and historical development notes.
6. Graph-derived relationships and AI-generated interpretations that still require verification.

For operational instructions, preserve higher-priority safety and repository constraints regardless of this information ordering.

Graphify, Obsidian and ICM support development decisions; none replaces source-code verification.

## Completion requirements

Before reporting a substantial development task as complete:

- Confirm the authorized scope was implemented.
- Verify relevant functionality using appropriate tests.
- Confirm no unrelated source changes were introduced.
- Update the Graphify graph when required.
- Synchronize affected Obsidian notes when justified.
- Store important verified project knowledge through ICM when useful.
- Update `TASK_PROGRESS.txt` when required.
- Review Git status and the scoped diff.
- Report what changed, what was tested, what was not verified and any remaining work.

The intended result is a reliable development workflow where **Graphify supports code understanding, Obsidian maintains documentation, and ICM preserves reusable knowledge across sessions**, with all three selected and maintained intelligently during normal development.