# Incremental specification-driven implementation

## Contents

1. Per-increment loop
2. Editing discipline
3. Testing sequence
4. Failure and rollback
5. Progress tracking

## 1. Per-increment loop

For each planned increment:

1. Read the relevant behavior contract.
2. Inspect the current target files and nearby tests.
3. Add/update the closest useful test when warranted.
4. Implement the smallest coherent change.
5. Run focused verification.
6. Review the diff against scope and invariants.
7. Mark the plan step complete.

Do not batch unrelated increments into one patch.

## 2. Editing discipline

- Use `apply_patch` for source edits.
- Preserve unrelated working-tree changes.
- Do not use destructive git commands unless explicitly authorized.
- Keep state transitions, validation, and error conversion centralized.
- Avoid speculative abstractions that are not required by the behavior contracts.
- Update docs/comments only when the public contract or operational workflow changed.

If an out-of-scope defect is discovered, record it. Fix it only when it blocks the requested work or the user expands scope.

## 3. Testing sequence

Run verification from narrow to broad:

```text
type/static/lint
→ focused unit
→ affected integration
→ package/module suite
→ build
→ smoke/fault test
```

For slow suites, run focused checks during implementation and the broadest practical check at handoff.

Report exact commands and outcomes. Never convert an environmental failure into a claim that the change passed.

## 4. Failure and rollback

When a test fails:

1. determine whether the implementation, test, or environment is wrong;
2. gather new evidence before another attempt;
3. stop repeating the same fix after evidence stops changing;
4. revisit the diagnosis/specification if the contract appears infeasible.

If implementation contradicts the agreed strategy:

- stop the affected increment;
- update the implementation brief;
- reassess downstream scope and tests;
- ask the user only when the new direction crosses a material decision boundary.

Do not hide uncertainty with broad exception handling, skipped tests, weakened assertions, or silent fallbacks.

## 5. Progress tracking

Use the plan tool for multi-step tasks. Commentary updates should state:

- what was verified or implemented;
- what remains;
- any changed assumption or blocker.

Create a durable task file only when the repository convention or long-running nature makes it useful. Store evidence and decisions, not private chain-of-thought.

