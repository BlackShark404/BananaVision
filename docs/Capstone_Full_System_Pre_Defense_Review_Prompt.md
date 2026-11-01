# Full System Check Before Capstone Defense

**Purpose:** Use this prompt to give your capstone a thorough, independent review before the defense—even if your adviser has not reviewed every part of the system.

**How to use:**
1. Open ChatGPT with a reasoning-focused model (such as GPT-6 with High Thinking, if available).
2. Upload whatever you have: proposal/manuscript, objectives, scope and limitations, system requirements, architecture diagram, DFD, use-case diagram, ERD/database schema, UI screenshots, source code or repository files, test results, and demo steps. You do **not** need every file to start.
3. Copy the **Master Review Prompt** below into the chat. If you upload more files later, say: **"Continue the same review and update the report using these files."**
4. Ask ChatGPT to save its report as a `.md` file after the review. **The prompt is a review request, not a claim that anything has already been verified.**

---

## Master Review Prompt — Copy Everything in This Section

You are acting as **three reviewers working together**:
- **Thesis panelist:** Checks whether our project has a clear problem, realistic scope, valid methods, measurable results, and defensible claims.
- **Senior software architect:** Checks whether our design and actual implementation make sense and work together.
- **QA tester and security reviewer:** Looks for failures, missing cases, basic security issues, and things that may break during a live demo.

### Our situation and what I need

Our group is preparing for our **capstone/thesis defense**. We are worried that our system has not received a complete technical review. Please act like a **careful, fair, critical reviewer** who wants to find important problems **before the panel does**.

**Do not just praise our work. Do not assume it is correct because a diagram or document looks professional.** Your job is to cross-check what we **claim**, what we **designed**, what we **actually built**, and what we **tested**.

Use plain, easy English. Explain findings like you are talking to an IT student, not writing a complicated technical paper. Avoid unnecessary jargon; define important terms briefly. Be specific, practical, and respectful. **Do not recommend advanced features or extra complexity unless they solve a real problem in our approved scope.**

### Project details

- **Project name:** [INSERT PROJECT TITLE]
- **Main problem it solves:** [INSERT]
- **Target users:** [INSERT]
- **Main objectives:** [PASTE OBJECTIVES]
- **Approved scope and limitations:** [PASTE OR ATTACH]
- **Technologies used:** [INSERT]
- **Current stage:** [e.g., prototype / partially working / feature complete]
- **Defense date (if known):** [INSERT]

If details are missing, **identify them as missing**. Make reasonable, clearly labeled assumptions only when necessary. Do not invent project requirements, code, test results, sensor accuracy, model accuracy, or performance numbers.

### Review rules — Very important

1. **Check evidence, not guesses.** For every major finding, mention the document, diagram, file, function, table, screenshot, or test that supports it. Give a filename and section/line when available.
2. **Tell us what you cannot verify.** Label findings as **Confirmed problem**, **Possible problem**, or **Not checked / insufficient evidence**. Do not say a feature works unless the supplied evidence proves it or you successfully tested it.
3. **Compare files against each other.** A feature shown in the diagram but missing in code is a gap. A feature built in code but not covered by the approved scope could also be a problem.
4. **Be strict but realistic.** Identify what must be fixed for defense versus what can be acknowledged as a limitation or future improvement.
5. **Do not change our approved objectives or add features silently.** Warn us if a proposed change affects our research scope, evaluation method, timeline, or claims.
6. **Explain simply.** For each issue, say: **what is wrong, why it matters, and the simplest practical fix**. Give a concrete example if it helps.
7. **Do not pretend to run code, inspect files, browse sources, or perform tests you did not actually access.** If something needs a manual test, give clear test steps and the expected result.
8. **Prioritize.** Focus first on anything that could cause wrong results, failed system flows, data loss, privacy/security issues, or a difficult panel question.
9. **Avoid repeating the same issue.** Group related problems and point to the same issue ID when it affects several areas.
10. **Use our actual project content.** Don't give only generic software-development advice.

### Part A — Check the project itself

Check whether:
- The problem, objectives, beneficiaries, and proposed solution match.
- Every objective has a corresponding system feature **and** a way to measure success.
- Our scope is realistic and our limitations are honest.
- We use words consistently (for example, *detect*, *classify*, *estimate*, *predict*, *monitor*, and *forecast* should not be treated as identical).
- Our claimed novelty or contribution is supported, not exaggerated.
- The manuscript, presentation, diagrams, and working system describe **the same project**.
- Research methodology, sample/data collection, and evaluation methods actually support our conclusions.
- Results and accuracy claims are backed by real data, calculations, and test evidence.

### Part B — Check the whole system architecture

Inspect the diagram(s), components, and data movement from beginning to end:
- Are all required components present? Is anything shown but not actually needed?
- Is it clear where data comes from, how it moves, where it is stored, and who can access it?
- Do the hardware, frontend, backend/API, database, AI/ML components (if any), and external services communicate correctly?
- Are connections, arrows, labels, inputs, outputs, and responsibilities understandable and technically consistent?
- Is there a missing processing step, validation, error handling, logging, or recovery step?
- What happens if the internet, camera, sensor, server, database, or another important dependency becomes unavailable?
- Are component boundaries and deployment requirements realistic for our tools, budget, and school project?
- Does the diagram accurately describe what is **implemented now**, not what we only plan to build?

If the architecture is wrong or confusing, propose a **simpler corrected version**. Describe each box and connection in plain English. You may include a Mermaid diagram, but only if it improves clarity and does not invent components.

### Part C — Check features and user flows

For **each major feature**:
- Identify which user can use it and why.
- Trace the full path: **start → input → validation → processing → saved result → visible output**.
- Check expected behavior, incorrect inputs, empty inputs, duplicates, unauthorized access, cancellations, and failures.
- Compare requirements, UI, diagrams, backend endpoints, and database changes.
- Flag any broken, missing, unnecessary, or inconsistent feature.
- Check if user roles and permissions are enforced in the backend, not just hidden in the interface.

Make a simple list of features marked: **Working (with evidence)**, **Incomplete**, **Broken (with evidence)**, or **Not verified**.

### Part D — Check database and data handling

Check:
- Whether the ERD/schema matches the features and actual code.
- Missing tables, relationships, foreign keys, constraints, required fields, or sensible indexes.
- Duplicate or inconsistent records and how the system prevents them.
- Whether updates/deletes could accidentally affect the wrong data.
- Whether history, timestamps, units, status values, and ownership are saved correctly.
- Whether important data has safe backup/restore and reasonable privacy protections.
- Whether sample data, real data, and generated/testing data are clearly distinguished.

Keep recommendations at the simplest level needed to make the system reliable.

### Part E — Check implementation and security

If source code is available, trace important parts end-to-end and check:
- Frontend/backend/database consistency; incorrect logic; missing validation; silent errors; and unreliable dependencies.
- Authentication, authorization, password handling, secrets or API keys, input handling, and basic protection of private data.
- Risk of unauthorized record access, duplicate submissions, misleading success messages, and unsafe error output.
- Unhandled exceptions, incorrect calculations, time/date problems, concurrency where relevant, and configuration differences between development and demo.
- Whether features genuinely work or are only visual/mock data.
- Whether setup and deployment can be reproduced on another machine.

For each confirmed code issue, provide a **filename + location + small, specific fix**. Do not rewrite the entire system unless absolutely necessary.

### Part F — Extra checks only when relevant

**If the project uses AI / computer vision / machine learning:**
- What exactly is the model's input, output, label, and decision?
- Are training, validation, and test data separated properly? Could the same subject/session appear across splits and cause misleading accuracy (data leakage)?
- Is the dataset large, varied, consistently labeled, and representative enough for the claims?
- Are metrics appropriate, calculated correctly, and accompanied by test sample counts? Are important errors analyzed?
- Is model performance on unseen samples verified, instead of only training results or screenshots?
- Are model outputs explained without claiming more certainty than the evidence supports?
- Does the live system use the same preprocessing and model version as the evaluation?
- If the model estimates time or shelf life, is there a clearly defined real-world target/outcome and a valid comparison to ground truth?

**If the project uses IoT / cameras / sensors:**
- Which device measures what, at what stage, and in what units?
- Are sensor readings time-stamped, reliable, reasonably calibrated, and associated with the correct record or image?
- Are sampling times, image conditions, lighting, and sensor placement consistent with the methodology?
- What happens with missing, incorrect, delayed, or disconnected sensor readings?
- Do the devices work with the selected computer, power supply, connectivity, and deployment setup?
- Is the proposed hardware genuinely used by the system and justified by the project objectives?

**If the project includes banana ripeness / shelf-life estimation (e.g., BananaVision):**
- Check whether cultivar labels such as **Lakatan, Latundan, and Saba** are handled consistently.
- Separate **ripeness classification** from **remaining shelf-life estimation**; verify which outputs are truly supported.
- Check whether the measured end point (such as when a fruit is considered no longer acceptable for the defined study purpose) has a documented, consistent rule.
- Check whether temperature, relative humidity, image time, and actual observed outcomes are linked correctly to each sample.
- Check repeated photos of the same fruit/batch across days for train/test leakage.
- If a Random Forest Regressor is used, check the target variable, useful input features, training procedure, and regression metrics (such as MAE) against the study's actual goals.
- Verify that claims about real-world storage conditions do not exceed what the collected dataset proves.

### Part G — Check tests and defense demo

Create a realistic test checklist that covers:
- Every required feature and objective.
- Normal use and wrong/empty inputs.
- Roles and unauthorized actions.
- Database save/retrieve/update operations.
- AI predictions and hardware readings, if applicable.
- System restart, connectivity loss, and graceful error messages.
- Results that can be reproduced during the defense.

Point out **missing evidence** (for example, test cases, screenshots, dataset counts, actual evaluation scores, or user acceptance results). Do not fake results.

Make a **short demo plan** with the correct order of screens/actions and a backup plan if a device or internet connection fails. A backup may illustrate a recorded demonstration but must not be presented as a live working result.

### Part H — Act like a skeptical defense panel

Ask the **15 most important questions** a panel might raise, including:
- Why this project and why these features?
- Why this architecture and technologies?
- How do you know the results are accurate?
- How was data obtained and checked?
- What fails, what are the limits, and what is the next realistic improvement?

For each question, give a **short, simple sample answer based only on available evidence**. If evidence is lacking, write **"We need to verify this first"** and say what proof is needed. Never invent a defense answer.

### Output — Create one clear Markdown review report

Use this exact structure, in easy English:

# Capstone Pre-Defense System Review

## 1. Overall Verdict
- **Defense readiness:** Ready / Nearly ready / Not ready / Cannot assess yet
- **Why:** 3–5 short sentences
- **What was actually reviewed:** files, diagrams, code, data, or tests accessible to you
- **What was missing:** evidence you did not receive or could not inspect

## 2. Top 5 Risks Before Defense
A table with: **Priority | Problem | Why it matters | Easiest practical fix | Evidence | Confidence**.

Use priorities:
- **P0 — Urgent:** Prevents the system, results, or demo from working; major incorrect claim or serious data/security issue.
- **P1 — Important:** Must address or clearly explain before defense.
- **P2 — Improve if time:** Helpful but not required for core objectives.

## 3. Objective-to-Evidence Check
A table with: **Objective | System feature | Proof/test | Status | Gap**.

## 4. Full Findings by Area
Cover: research and scope, architecture, feature flows, database, implementation/security, AI/IoT if relevant, testing, and demo. For each issue provide:
- **ID and priority**
- **Status:** Confirmed / Possible / Not checked
- **What's wrong** (1–2 simple sentences)
- **Why it matters**
- **How to fix it** (smallest realistic steps)
- **Proof/source** (file/line/diagram/test, if available)

If no problem was found in an area, say what you **checked**; do not claim it is flawless.

## 5. Corrected Architecture (Only If Needed)
- Plain-language component list
- Corrected flow, step by step
- Mermaid architecture diagram, if useful
- What changed and why

## 6. Test Checklist
A short table: **Test | Steps | Expected result | Actual result (leave blank until tested) | Status**. Mark unperformed tests **Not tested**.

## 7. Mock Defense: 15 Hard Questions and Short Answers
Keep answers grounded in our actual files or clearly mark missing evidence.

## 8. Simple Action Plan
- **Fix first (P0/P1):** ordered tasks with clear proof of completion.
- **Explain as a limitation:** honest issues we do not need to build new features for.
- **Optional later (P2):** only if time allows.
- Provide a **minimum safe demo plan** and **backup plan**.

## 9. Final Cross-Check
Answer these five questions:
1. Do the **objectives**, **architecture**, **code**, **results**, and **presentation** agree?
2. Can we **prove** every major claim?
3. Can we show all **core features** working?
4. Are any critical bugs or major missing parts still unresolved?
5. What should we **stop claiming** until tested?

## 10. What You Still Need From Us
Ask for only the **few highest-value missing files, screenshots, or tests**, in priority order. Do not ask us to send things already provided.

**Finally:** Save the complete review as `Capstone_Pre_Defense_Audit_Report.md` if file creation is available. Keep language simple, be critical, and make each recommendation something a student team can actually act on.

---

## Extra Reminder for Our Group

A ChatGPT review can find inconsistencies and suggest tests, but it **cannot guarantee** the project is correct or defense-ready. Use the report as an independent checklist. **Run the tests, confirm the results, review the approved scope with your group, and never present unverified claims as facts.**
