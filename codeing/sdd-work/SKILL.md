---
name: sdd-work
description: Evidence-driven software development workflow for implementing features, fixing bugs, refactoring, and adding tests. Use when Codex must inspect an existing codebase, derive a verifiable implementation specification from repository evidence, make scoped code changes, validate behavior, and audit the final diff against the agreed intent. Especially useful for multi-file, architecture-sensitive, ambiguous, or high-risk engineering tasks.
---

# SDD Engineering Work

Apply a research → specification → implementation → audit loop. Preserve momentum: do not force ceremony onto trivial changes, and do not stop for approval unless a material choice cannot be discovered or safely inferred.

Do not expose hidden chain-of-thought. Record concise conclusions, evidence, assumptions, decisions, behavior contracts, and verification results.

## Select workflow depth

Classify the task before acting:

- **Small and explicit**: inspect the local code path, define the behavior mentally or in the plan, implement, test, and audit. Do not create extra artifacts.
- **Multi-file or architecture-sensitive**: use the full workflow and maintain a task brief.
- **Review, diagnosis, or explanation only**: research and report; do not implement unless requested.
- **Materially ambiguous or high-impact**: research first, present the implementation brief, and request direction only if the unresolved choice changes scope, behavior, data, security, or external effects.

## 1. Scan context

Read [references/context-research.md](references/context-research.md).

Start with repository instructions (`AGENTS.md`, `CLAUDE.md`, local instruction files), project manifests, relevant design documents, source entry points, and tests. Do not require a `docs/` directory. If documentation is absent or stale, infer from code and tests and state the uncertainty.

Use `rg`/`rg --files` first. Inspect the smallest sufficient surface, then expand along imports, callers, data flow, and test coverage.

For complex work, create a task brief only if the repository has an established task/document convention or the artifact materially improves resumability. Prefer an existing location. Otherwise keep the brief in the active plan and commentary.

## 2. Research with evidence

Read [references/context-research.md](references/context-research.md) for the research loop.

Build two complementary views:

1. **Responsibility map**: what each relevant module owns, exposes, depends on, and deliberately does not know.
2. **Behavior/data path**: where input enters, how it changes, where state is stored, and where output or side effects occur.

For each important conclusion:

- cite repository evidence using file and line;
- search for counterexamples;
- distinguish confirmed facts, strong inference, and unresolved uncertainty;
- run read-only diagnostics or focused tests where useful.

Use web research for unstable or niche technical facts, relying on primary sources. Do not browse merely to replace repository inspection.

Use subagents only when the user explicitly requests delegation/parallel agents and the capability is available. Give them disjoint, evidence-oriented tasks; integrate their results yourself.

Stop researching when no unresolved fact would materially change the implementation.

## 3. Build the implementation brief

Read [references/specification.md](references/specification.md).

For non-trivial work, define:

1. **Objective**: one sentence describing the intended outcome.
2. **Current-state diagnosis**: the relevant structure and cause, backed by evidence.
3. **Strategy**: the chosen approach and rejected alternatives that matter.
4. **Scope**: files/components to change and explicit exclusions.
5. **Behavior specification**: inputs, outputs, invariants, boundaries, errors, and side effects.
6. **Verification map**: how each behavior will be checked.
7. **Risks and uncertainties**: impact, mitigation, and how remaining uncertainty will be resolved.
8. **Implementation order**: small dependency-ordered increments, each independently verifiable.

Use the plan tool for multi-step work. Do not duplicate a long brief into both a file and the plan unless the repository requires a durable artifact.

### Approval gate

Continue directly to implementation when the request clearly authorizes the change and the brief has no material unresolved choice.

Pause for user direction only when:

- two viable choices materially change behavior or scope;
- authority is needed for an external or destructive action;
- the user explicitly requested design approval before coding;
- available evidence cannot resolve a high-impact ambiguity.

When gating, present conclusions and tradeoffs—not private reasoning—and ask the minimum question required.

## 4. Implement incrementally

Read [references/implementation.md](references/implementation.md).

For each planned increment:

1. Re-read its behavior contract.
2. Add or update the closest useful test when the behavior warrants testing.
3. Implement the smallest coherent change.
4. Run focused verification.
5. Compare the diff with scope and invariants.
6. Update the plan before moving on.

Use `apply_patch` for edits. Preserve unrelated user changes. Do not silently repair out-of-scope issues.

If implementation reveals that the diagnosis or strategy is wrong, stop that path, revise the brief, and reassess downstream steps. Ask the user only if the revision crosses a material decision boundary.

## 5. Validate proportionally

Use the narrowest checks that establish confidence, then broaden:

```text
static/type/lint check
→ focused unit test
→ affected integration test
→ broader suite/build
→ realistic smoke or fault test
```

Do not claim tests passed unless they were run. Distinguish:

- passed;
- failed because of the change;
- failed for a pre-existing/environmental reason;
- not run, with reason.

Retry a failing approach only while new evidence is being gained. Repeated failure without new evidence means revisit the specification, not keep patching blindly.

## 6. Audit the result

Read [references/audit.md](references/audit.md).

Compare the actual implementation with the brief:

- objective achieved;
- diagnosis addressed rather than bypassed;
- strategy preserved or deviation justified;
- scope respected;
- every behavior contract implemented and verified;
- risks handled;
- no accidental external effects or sensitive-data exposure;
- no stale comments, tests, or documentation.

Report material deviations. Do not conceal an unmet behavior behind passing tests.

## 7. Hand off

Lead with the outcome. Include:

- what changed;
- key files;
- verification run and results;
- material design decisions;
- remaining risks or blocked items.

Link local files using absolute clickable paths when available. Keep the final response self-contained.

