# Automated Negative Flow Generator Implementation Plan (qa_auto mutate)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically synthesize realistic negative and edge-case test case variations (`TestCase` objects) from recorded user flows, covering form input edge cases (empty strings, boundary overflows, SQLi/XSS probes, unicode), rapid action replays (double submit), and network fault simulations.

**Architecture:** Create `qa_auto.mutation` package with modular mutation strategies (`InputMutator`, `ActionMutator`, `NetworkFaultMutator`) and a central `MutationEngine`. Register `mutate` command in Typer CLI.

**Tech Stack:** Python 3.13, Pydantic, Typer, Rich.

## Global Constraints

- Python `>=3.13`, Ruff `target-version = "py313"`, line length 100.
- All synthesized test cases must conform strictly to the existing immutable `TestCase` schema in `src/qa_auto/models.py`.
- Synthesized test cases must be immediately replayable via `qa_auto replay` and convertible via `qa_auto codegen`.
- Offline by default; no external network.
- Ruff rules: `E, F, I, UP, B, SIM`. Strict typing (`disallow_untyped_defs`).
- Exit codes: `0` on success, `2` on missing files / invalid arguments.

---

### Task 1: Mutation models & input mutation strategy

**Files:**
- Create: `src/qa_auto/mutation/__init__.py`
- Create: `src/qa_auto/mutation/models.py`
- Create: `src/qa_auto/mutation/inputs.py`
- Test: `tests/test_mutation_inputs.py`

**Interfaces:**
- Produces:
  - `MutationType`: Literal["empty", "boundary_long", "special_chars", "unicode", "invalid_format"]
  - `MutationMetadata`: description, target_step, original_value, mutated_value, strategy
  - `mutate_inputs(testcase: TestCase) -> list[TestCase]`: Scans steps for input actions and generates negative testcase variants.

- [ ] **Step 1: Write failing input mutation tests**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement input mutation strategies**
- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Lint and types**
- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/mutation/ tests/test_mutation_inputs.py
git commit -m "Add input mutation strategies for negative testing"
```

---

### Task 2: Action sequence and network fault strategies

**Files:**
- Create: `src/qa_auto/mutation/actions.py`
- Create: `src/qa_auto/mutation/network.py`
- Test: `tests/test_mutation_strategies.py`

**Interfaces:**
- Produces:
  - `mutate_actions(testcase: TestCase) -> list[TestCase]`: Clones click steps to simulate double-clicks / rapid submissions.
  - `mutate_network_faults(testcase: TestCase) -> list[TestCase]`: Injects error responses (HTTP 500 / 403) into recorded API calls for mock route testing.

- [ ] **Step 1: Write failing strategy tests**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement action and network fault strategies**
- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Lint and types**
- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/mutation/ tests/test_mutation_strategies.py
git commit -m "Add action sequence and network fault mutation strategies"
```

---

### Task 3: Mutation engine orchestrator

**Files:**
- Create: `src/qa_auto/mutation/engine.py`
- Test: `tests/test_mutation_engine.py`

**Interfaces:**
- Produces:
  - `MutationEngine`:
    - `generate(testcase: TestCase, strategies: list[str] | None = None, limit: int = 10) -> list[TestCase]`
    - `export_mutations(mutations: list[TestCase], output_dir: Path) -> list[Path]`

- [ ] **Step 1: Write failing orchestrator tests**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement MutationEngine**
- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Lint and types**
- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/mutation/engine.py tests/test_mutation_engine.py
git commit -m "Add mutation engine orchestrator and disk exporter"
```

---

### Task 4: CLI command `qa_auto mutate`

**Files:**
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_cli_mutate.py`

**Interfaces:**
- CLI command: `qa_auto mutate <testcase.json> [-o <output-dir>] [--strategy <strategy>] [--limit <n>]`
  - Generates mutated test cases on disk.
  - Displays a Rich summary table of generated mutations.

- [ ] **Step 1: Write failing CLI tests**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement CLI mutate command**
- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Lint and types**
- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/cli.py tests/test_cli_mutate.py
git commit -m "Add mutate CLI command"
```

---

### Task 5: Documentation & phase verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `qa_auto mutate` in `README.md`**
- [ ] **Step 2: Run full test suite and quality gate**
- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document automated negative flow generator capabilities"
```
