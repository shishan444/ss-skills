# Implementation audit and handoff

## Contents

1. Audit checklist
2. Diff review
3. Verification accounting
4. Deviation handling
5. Final handoff

## 1. Audit checklist

Compare the final implementation with the brief:

- objective is actually achieved;
- implementation addresses the diagnosed cause or extension point;
- chosen strategy remains intact;
- modified files are within scope;
- every behavior contract has implementation and verification;
- boundary and failure behavior is explicit;
- security, privacy, migration, and external-effect risks are handled;
- tests assert the intended behavior rather than the implementation accident.

## 2. Diff review

Inspect the complete diff, not only the files last edited.

Look for:

- unrelated cleanup;
- stale names/comments;
- accidental API changes;
- duplicated logic;
- leaked secrets or sensitive output;
- missing cancellation/cleanup;
- newly introduced broad types or unchecked values;
- tests that pass without exercising the change.

## 3. Verification accounting

Create a concise table or list:

```text
behavior contract → verification command/result
```

Distinguish:

- passed;
- failed because of this change;
- failed for pre-existing/environment reasons;
- not run.

Do not describe “tests pass” when only a subset ran.

## 4. Deviation handling

Report all material deviations:

- changed objective;
- scope expansion;
- unmet behavior contract;
- strategy substitution;
- newly discovered high-impact risk;
- implementation-order change that affected validation.

Equivalent low-risk implementation details may be accepted without another gate, but mention them when they matter to maintainers.

User approval is required before accepting a deviation that changes behavior, scope, data safety, or external effects.

## 5. Final handoff

Lead with the outcome. Include:

1. what changed;
2. key files;
3. verification commands and results;
4. material decisions or deviations;
5. remaining risks, failures, or next actions.

Use absolute clickable file links when referencing local files.

