# Context and engineering research

## Contents

1. Context scan
2. Research loop
3. Evidence standards
4. Counterexample checks
5. Delegation guidance
6. Exit criteria

## 1. Context scan

Find the actual project boundary from the current working directory, repository root, manifests, and instruction files. Treat `AGENTS.md`, `CLAUDE.md`, and repository-local guidance as inputs; do not assume one specific filename is authoritative unless the repository says so.

Inspect in this order:

1. Repository and local instructions.
2. Working-tree status; preserve unrelated changes.
3. Build/package manifests and runtime configuration.
4. Relevant architecture/design documents.
5. Source entry points and public interfaces.
6. Existing tests, fixtures, and CI commands.
7. The concrete call/data path affected by the request.

Documentation is evidence of intent, not proof of current behavior. Code and tests are evidence of implementation. When they conflict, report the mismatch and determine which one the task asks to change.

Do not block merely because `docs/` is absent. For an established project with poor documentation, increase code/test inspection and explicitly record uncertainty.

## 2. Research loop

Repeat only while a material uncertainty remains:

```text
map responsibilities and data flow
→ form a concrete hypothesis
→ search for supporting and opposing evidence
→ run a focused diagnostic when useful
→ update the implementation view
```

### Responsibility map

For each relevant component, answer:

- What state or responsibility does it own?
- What interface does it expose?
- What does it depend on?
- What knowledge is intentionally outside its boundary?

Do not infer responsibility from filenames alone.

### Behavior/data path

Trace:

```text
input/event
→ validation
→ transformation
→ state/storage
→ output/side effect
```

Record boundary crossings, shared mutable state, retries, asynchronous events, and error conversion.

## 3. Evidence standards

Use evidence appropriate to the claim:

- Static structure: file and line references.
- Runtime behavior: focused tests, logs, reproductions, or traces.
- Public contract: exported types, API schema, CLI help, tests, or docs.
- External technical fact: primary documentation or source repository.

Label conclusions:

- **Confirmed**: direct code/test/runtime evidence.
- **High confidence**: multiple consistent indirect signals.
- **Unresolved**: insufficient evidence; explain whether it blocks implementation.

Do not write private deliberation into task artifacts. Record conclusions and the evidence that makes them defensible.

## 4. Counterexample checks

For each high-impact hypothesis, ask:

> What fact would prove this diagnosis wrong?

Examples:

- “This function is the only writer” → search every assignment and mutation path.
- “The API always returns X” → inspect error/empty/cache branches.
- “This change is isolated” → find all callers, implementations, fixtures, and serialized forms.
- “No migration is needed” → inspect persisted schemas and backward compatibility.

If counterevidence appears, narrow or replace the hypothesis before designing the fix.

## 5. Delegation guidance

Use subagents only when explicitly authorized by the user and available in the environment.

Good delegated research tasks are disjoint and evidence-oriented:

- module responsibility map;
- end-to-end data-flow trace;
- independent verification of a concrete hypothesis;
- long-running test or benchmark.

Require file:line evidence or raw test output. Do not delegate the final strategy decision or user communication.

## 6. Exit criteria

Research is sufficient when:

- the affected responsibility boundary is known;
- the relevant behavior/data path is known;
- the cause or extension point is supported by evidence;
- callers and tests have been checked;
- no unresolved fact would materially alter scope or strategy.

