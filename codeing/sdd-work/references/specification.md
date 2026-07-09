# Evidence-backed implementation specification

## Contents

1. Brief structure
2. Behavior contracts
3. Scope and strategy
4. Verification map
5. Risk and approval
6. Implementation ordering

## 1. Brief structure

For non-trivial work, produce a concise implementation brief:

```markdown
## Objective

## Current state
- conclusion — evidence: path:line

## Strategy

## Scope
- change:
- exclude:

## Behavior contracts
- B1 ...

## Verification
- B1 → test/check

## Risks and uncertainties

## Implementation order
1. ...
```

The brief is a decision record, not a transcript of hidden reasoning.

## 2. Behavior contracts

Specify externally meaningful behavior:

- inputs and validation;
- outputs and observable effects;
- invariants;
- boundary cases;
- errors and recovery;
- preconditions and postconditions;
- compatibility expectations.

Mark verification:

- `[unit]` pure logic and transformations;
- `[integration]` module boundaries, storage, network, process interaction;
- `[smoke]` realistic happy path;
- `[fault]` recovery, timeout, cancellation, crash;
- `[review]` simple wiring or declarative configuration.

Bad:

> The feature should work normally.

Good:

> `normalize(values)` returns an equal-length array with finite values in `[0,1]`; an all-zero input returns all zeros; any `NaN` input raises `ValueError`. `[unit]`

## 3. Scope and strategy

List files/components to change and why. Explicitly exclude tempting adjacent work.

Choose a strategy that addresses the diagnosed boundary or cause. Mention rejected alternatives only when they affect maintenance, compatibility, safety, or delivery.

If implementation requires a materially different scope, revise the brief before continuing.

## 4. Verification map

Every behavior contract needs one verification method. Avoid testing implementation details when public behavior is sufficient.

Use existing test conventions. Add a new framework only if current tooling cannot verify a core contract and the added complexity is justified.

For bug fixes, include a test that fails before the fix when practical.

## 5. Risk and approval

Separate:

- known risks with impact and mitigation;
- unresolved uncertainties with a resolution method;
- external/destructive actions requiring authority.

Request user direction only if a remaining choice materially changes:

- user-visible behavior;
- data migration or compatibility;
- security/privacy;
- external side effects;
- project scope or cost.

Do not gate routine implementation solely because the task is large.

## 6. Implementation ordering

Derive increments from behavior contracts:

1. identify dependencies;
2. put prerequisites first;
3. when independent, address high-risk assumptions early;
4. keep each increment independently testable;
5. avoid a final “integrate everything” step with no earlier integration checks.

