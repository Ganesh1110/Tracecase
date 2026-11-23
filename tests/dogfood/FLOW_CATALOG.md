# Tracecase Complete Flow Catalog (FLOW_CATALOG.md)

## Summary Matrix
| Section | Category | Flow Count | Automation Method | Status |
|---|---|---|---|---|
| **A** | Install and Environment | 7 | Subprocess CLI / Pytest | PENDING |
| **B** | CLI: Record | 27 | Subprocess CLI + Programmatic Recorder | PENDING |
| **C** | CLI: Replay | 17 | Subprocess CLI + ReplayEngine | PENDING |
| **D** | CLI: Diff | 6 | Subprocess CLI + PIL | PENDING |
| **E** | CLI: Export HAR | 4 | Subprocess CLI | PENDING |
| **F** | CLI: Codegen | 7 | Subprocess CLI + Pytest execution | PENDING |
| **G** | CLI: Mutate | 12 | Subprocess CLI + Replay verification | PENDING |
| **H** | CLI: Analyze | 9 | Subprocess CLI + Fake LLM | PENDING |
| **I** | Corpus (Index/Search/Coverage/Clean/MCP) | 22 | Subprocess CLI + MCP stdio client | PENDING |
| **J** | Regression and CI Intelligence | 20 | Subprocess CLI + Git fixture repo | PENDING |
| **K** | Studio: Launch and Server | 10 | Subprocess CLI + HTTP/WS Client | PENDING |
| **L** | Studio Modules & Workflows | 26 | Dogfood Playwright Recording / API | PENDING |
| **M** | Cross-cutting Concerns | 8 | Isolated Network / Security audit | PENDING |
| **N** | End-to-End Journeys | 8 | Chained E2E Test Pipelines | PENDING |
| **Total** | | **183** | | |

---

## Detailed Catalog

### Section A: Install and Environment
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| A1 | Pip install from source | Clean virtualenv | `pip install -e ".[dev]"` | Exits 0, `tracecase` binary installed | Subprocess Pytest | PENDING |
| A2 | Playwright browsers install | Virtualenv active | `python -m playwright install chromium` | Exits 0, Chromium binary installed | Subprocess Pytest | PENDING |
| A3 | `tracecase check` healthy | Playwright installed | `tracecase check` | Exits 0, reports all dependencies healthy | Subprocess Pytest / Hand-written | PENDING |
| A3.1 | `tracecase check` missing browser | Unset Playwright path | `tracecase check` | Exits 1 or clear diagnostic error | Subprocess Pytest | PENDING |
| A4 | `tracecase version` info | None | `tracecase version` | Exits 0, prints Tracecase, Python, Playwright, Pydantic versions | Subprocess Pytest | PENDING |
| A5 | `--help` on all commands | None | Run `--help` on root and 27 subcommands | Exits 0, valid Rich-formatted help output | Subprocess Pytest | PENDING |
| A6 | Unknown command / missing args | None | `tracecase invalid_cmd`, `tracecase record` without URL | Exits with non-zero exit code, clear user error, no traceback | Subprocess Pytest | PENDING |

---

### Section B: CLI: Record
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| B1 | Minimal recording | Playground running | `tracecase record <url> -o <dir> --headless` | Creates `testcase.json`, `testcase.md`, `testcase.html`, `screenshots/` | Subprocess Pytest / Hand-written | PENDING |
| B2 | Custom name | None | `tracecase record <url> -o <dir> -n "Custom Suite"` | `name` in `testcase.json` equals "Custom Suite" | Subprocess Pytest | PENDING |
| B3 | Default name generation | None | `tracecase record <url> -o <dir>` without `-n` | `name` auto-generated from target domain/title | Subprocess Pytest | PENDING |
| B4 | Browser chromium | None | `tracecase record <url> -o <dir> -b chromium` | Browser metadata in `testcase.json` is "chromium" | Subprocess Pytest | PENDING |
| B5 | Browser firefox | Firefox installed | `tracecase record <url> -o <dir> -b firefox` | Browser metadata is "firefox" | Subprocess Pytest | PENDING |
| B6 | Browser webkit | WebKit installed | `tracecase record <url> -o <dir> -b webkit` | Browser metadata is "webkit" | Subprocess Pytest | PENDING |
| B7 | Invalid browser choice | None | `tracecase record <url> -o <dir> -b ie11` | Exits 2 or clear click error, rejects invalid browser | Subprocess Pytest | PENDING |
| B8 | Headless mode flag | None | `tracecase record <url> -o <dir> --headless` | Browser executes with GUI hidden | Subprocess Pytest | PENDING |
| B9 | Action timeout option | None | `tracecase record <url> -o <dir> -t 5000` | Timeout setting applied | Subprocess Pytest | PENDING |
| B10 | Missing required output option | None | `tracecase record <url>` without `-o` | Exits with error stating `--output` is required | Subprocess Pytest | PENDING |
| B11 | Invalid or unreachable URL | None | `tracecase record http://127.0.0.1:9999/down -o <dir>` | Exits gracefully with connection error | Subprocess Pytest | PENDING |
| B12 | Control panel lifecycle | Playground | Start button -> Click actions -> Stop button | Panel transitions from Ready to Recording, step count increments, stops cleanly | Programmatic Recorder | PENDING |
| B13 | Stop with zero steps | Playground | Start -> Immediately Stop | Schema-valid `testcase.json` produced with 0 steps | Programmatic Recorder | PENDING |
| B14 | Close browser without Stop | Playground | Close page/browser tab | Graceful exit, partial or saved testcase without corruption | Programmatic Recorder | PENDING |
| B15 | Panel excluded from screenshots | Playground | Click element near top-right panel | Screenshot captures page without control panel overlay | Programmatic Recorder | PENDING |
| B16 | Action types capture | Playground form | Click, dblclick, input, select, check, uncheck, Enter, Escape, Tab, scroll | All 11 action types recorded with correct enum and parameters | Programmatic Recorder / Hand-written | PENDING |
| B17 | Element metadata capture | Playground | Interact with button/input | `selector`, `xpath`, `tag_name`, `bounding_box`, `placeholder`, `attributes` populated | Programmatic Recorder | PENDING |
| B18 | Step screenshot with highlight | Playground | Perform step | Screenshot written to `screenshots/NNN_action_target.png` with target outline | Programmatic Recorder | PENDING |
| B19 | Network capture per step | Playground API | Click button triggering XHR/fetch | `network_requests` attached to step with method, URL, headers, status, timing | Programmatic Recorder | PENDING |
| B20 | Console log capture | Playground console | Trigger `console.log/warn/error` | `console_logs` captured and attached to step | Programmatic Recorder | PENDING |
| B21 | Page JS error capture | Playground error | Trigger unhandled JS exception | `page_errors` captured in timeline | Programmatic Recorder | PENDING |
| B22 | Multi-tab pop-up capture | Playground tabs | Click `target="_blank"` link | New page detected, `page_id=1` tagged on new tab actions | Programmatic Recorder | PENDING |
| B23 | Output files validation | None | Validate outputs against Pydantic models | `testcase.json` passes `TestCase.model_validate`, HTML/MD valid | Subprocess Pytest / Hand-written | PENDING |
| B24 | Hostile data XSS safety | Playground hostile | Steps with `<script>alert(1)</script>` in text/selector | `testcase.html` renders safely without script execution | Subprocess Pytest | PENDING |
| B25 | Output directory collision | Existing dir | Record into existing directory | Overwrites or updates files safely without crash | Subprocess Pytest | PENDING |
| B26 | Path with spaces / unicode | Dir with spaces | `tracecase record <url> -o "test dir/файл"` | Successfully saves to unicode/spaced path | Subprocess Pytest | PENDING |
| B27 | Password masking audit | Playground login | Type into `input[type="password"]` | Audits whether password is stored plain text or flagged | Security Audit / Pytest | PENDING |

---

### Section C: CLI: Replay
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| C1 | Basic headless replay | Valid recording | `tracecase replay <testcase.json>` | Exits 0, all steps execute successfully | Subprocess Pytest / Hand-written | PENDING |
| C2 | Headed replay | Valid recording | `tracecase replay <testcase.json> --headed` | Headed browser executes, exits 0 | Subprocess Pytest | PENDING |
| C3 | Replay output artifact | Valid recording | `tracecase replay <testcase.json> -o <dir>` | Writes `replay.json` and execution screenshots | Subprocess Pytest | PENDING |
| C4 | Exit codes differentiation | Passing/failing/bad | Test pass (exit 0), assertion failure (exit 1), invalid JSON (exit 2) | Exact exit codes match specification | Subprocess Pytest | PENDING |
| C5 | `--assert` vs `--no-assert` | Assertion mismatch | Replay with `--assert` vs `--no-assert` | `--assert` fails on mismatch; `--no-assert` ignores assertions | Subprocess Pytest | PENDING |
| C6 | Derived assertions evaluation | Playground errors | Replay against page with changed text / 500 error | Derived DOM, HTTP status, and console assertions trigger failure | Subprocess Pytest | PENDING |
| C7 | Timeout sensitivity | Slow endpoint | Replay with `-t 100` vs `-t 10000` | Short timeout fails; long timeout passes | Subprocess Pytest | PENDING |
| C8 | Healing disabled on changed UI | Playground Version-B | `tracecase replay <tc.json> --no-heal` | Fails because original selectors no longer match | Subprocess Pytest | PENDING |
| C9 | Healing enabled on Version-B | Playground Version-B | `tracecase replay <tc.json> --heal` | Passes, heals selectors, writes `healed_from` in `replay.json` | Subprocess Pytest / Hand-written | PENDING |
| C10 | Isolated healing tiers test | Custom DOM fixtures | Test ID, Name, TestID, Text, XPath healing tiers in isolation | Verifies candidate chain ordering and resolution | Unit / Subprocess Pytest | PENDING |
| C11 | Visual diff identical UI | Version-A | `tracecase replay <tc.json> --diff` | Diff passes (0% diff) | Subprocess Pytest | PENDING |
| C12 | Visual diff threshold & flags | Version-C | `tracecase replay <tc.json> --diff --diff-threshold 0.01 --diff-fail` | Fails with exit 1 on drift; passes with `--no-diff-fail` | Subprocess Pytest | PENDING |
| C13 | Offline HAR replay | Exported HAR | Stop backend, `tracecase replay <tc.json> --from-har <file.har>` | Replays offline successfully via route mocking | Subprocess Pytest | PENDING |
| C14 | Multi-tab replay | Multi-tab testcase | `tracecase replay <multi_tab_tc.json>` | Switches pages cleanly using `page_id` | Subprocess Pytest | PENDING |
| C15 | Backward compatibility | Legacy testcase | Replay testcase missing `page_id` | Defaults to page 0, replays without error | Subprocess Pytest | PENDING |
| C16 | Browser matrix replay | Valid testcase | Replay across Chromium, Firefox, WebKit | Passes across supported browsers | Subprocess Pytest | PENDING |
| C17 | Replay mutated testcase | Mutated testcase | Replay synthesized negative testcase | Validates rejection or expected error response | Subprocess Pytest | PENDING |

---

### Section D: CLI: Diff
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| D1 | Identical images comparison | Two identical PNGs | `tracecase diff img1.png img2.png` | Exits 0, reports 0.0% difference | Subprocess Pytest | PENDING |
| D2 | Different images comparison | Two distinct PNGs | `tracecase diff img1.png img2.png -o diff.png` | Exits 1, saves magenta highlighted diff image | Subprocess Pytest | PENDING |
| D3 | Threshold boundary test | 5% pixel diff | Test with `--threshold 0.04` (fail) and `--threshold 0.06` (pass) | Boundary respected | Subprocess Pytest | PENDING |
| D4 | Different image dimensions | 100x100 vs 200x200 | `tracecase diff img1.png img2.png` | Handles dimension mismatch cleanly or resizes | Subprocess Pytest | PENDING |
| D5 | Missing or corrupted image | Nonexistent file | `tracecase diff missing.png img.png` | Exits with error, no crash | Subprocess Pytest | PENDING |
| D6 | Diff without `-o` output | Distinct PNGs | `tracecase diff img1.png img2.png` | Exits 1, reports diff percentage to stdout without file write | Subprocess Pytest | PENDING |

---

### Section E: CLI: Export HAR
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| E1 | Valid HAR export | Recording with network | `tracecase export-har tc.json -o out.har` | Creates valid HAR 1.2 JSON structure | Subprocess Pytest | PENDING |
| E2 | Export then replay from HAR | Recording with API | Export HAR -> replay with `--from-har out.har` | Offline replay succeeds | Subprocess Pytest | PENDING |
| E3 | Export testcase with 0 requests | Recording without net | `tracecase export-har empty_net.json -o out.har` | Creates valid empty HAR entries list | Subprocess Pytest | PENDING |
| E4 | Missing `-o` flag | Valid recording | `tracecase export-har tc.json` | Defaults to `<testcase_dir>/network.har` or prints error | Subprocess Pytest | PENDING |

---

### Section F: CLI: Codegen
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| F1 | Default pytest generation | Valid testcase | `tracecase codegen tc.json` | Produces `test_<name>.py` in testcase directory | Subprocess Pytest | PENDING |
| F2 | Custom output file | Valid testcase | `tracecase codegen tc.json -o ./tests/custom.py` | Writes to specified path | Subprocess Pytest | PENDING |
| F3 | HAR mocking inclusion | Valid testcase | `tracecase codegen tc.json --har` | Generated code includes `page.route_from_har()` | Subprocess Pytest | PENDING |
| F4 | Execute generated pytest code | Generated test | `pytest <generated_test.py>` | Generated pytest Playwright test passes! | Subprocess Pytest / Hand-written | PENDING |
| F5 | Codegen for multi-tab flow | Multi-tab testcase | `tracecase codegen multi_tab.json` | Generated code handles `expect_popup()` or new pages | Subprocess Pytest | PENDING |
| F6 | Derived assertions in codegen | Testcase with assert | `tracecase codegen tc.json` | Contains `expect(page.locator(...)).to_be_visible()` etc. | Subprocess Pytest | PENDING |
| F7 | Sanitization of special chars | Name with `!@#$%^&*()` | `tracecase codegen tc.json` | Generates valid Python function and module identifier | Subprocess Pytest | PENDING |

---

### Section G: CLI: Mutate
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| G1 | Default mutation run | Form recording | `tracecase mutate tc.json` | Generates up to 20 mutations in `mutations/` | Subprocess Pytest | PENDING |
| G2 | Inputs strategy | Form recording | `tracecase mutate tc.json -s inputs` | Generates input mutations (empty, boundary, unicode, SQLi, XSS) | Subprocess Pytest | PENDING |
| G3 | Actions strategy | Multi-step recording | `tracecase mutate tc.json -s actions` | Generates action mutations (skip, double_click) | Subprocess Pytest | PENDING |
| G4 | Network strategy | Network recording | `tracecase mutate tc.json -s network` | Generates network fault mutations | Subprocess Pytest | PENDING |
| G5 | Invalid strategy | None | `tracecase mutate tc.json -s invalid` | Exits with error, clear usage | Subprocess Pytest | PENDING |
| G6 | Limit flag `--limit` | Form recording | `tracecase mutate tc.json -n 3` | Produces exactly 3 mutations | Subprocess Pytest | PENDING |
| G7 | Custom output directory | None | `tracecase mutate tc.json -o ./custom_mutations` | Writes to custom folder | Subprocess Pytest | PENDING |
| G8 | Input mutation types validity | Form recording | Check each mutated value | Boundary long (2048 chars), SQLi (`' OR '1'='1`), XSS (`<script>`) present | Subprocess Pytest | PENDING |
| G9 | Action mutation types validity | Step recording | Check mutated steps | Target step skipped or duplicated | Subprocess Pytest | PENDING |
| G10 | Network mutation types validity | Net recording | Check mutated net | HTTP error codes (500, 403, 429) injected | Subprocess Pytest | PENDING |
| G11 | Schema validity & replayability | Generated mutations | Validate all `testcase.json` with Pydantic; replay sample | All mutations are valid TestCase models | Subprocess Pytest / Hand-written | PENDING |
| G12 | Testcase with zero inputs/network | Navigation-only test | `tracecase mutate nav_only.json` | Graceful exit, 0 mutations generated without crash | Subprocess Pytest | PENDING |

---

### Section H: CLI: Analyze
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| H1 | Default offline heuristics | Recorded testcase | `tracecase analyze tc.json` | Writes `analysis.json` with heuristic assessment | Subprocess Pytest | PENDING |
| H2 | Custom output directory | Recorded testcase | `tracecase analyze tc.json -o ./analysis_out` | Saves to custom directory | Subprocess Pytest | PENDING |
| H3 | Provider null explicitly | None | `tracecase analyze tc.json --provider null` | Runs purely offline, zero external calls | Subprocess Pytest | PENDING |
| H4 | AI with Ollama defaults | Fake LLM on 9100 | `tracecase analyze tc.json --ai --base-url http://127.0.0.1:9100` | Successfully completes AI enrichment | Subprocess Pytest | PENDING |
| H5 | OpenAI provider with Fake LLM | Fake LLM on 9100 | `tracecase analyze tc.json --provider openai --base-url http://127.0.0.1:9100/v1 --model gpt-4o` | Queries Fake LLM, parses response into analysis | Subprocess Pytest | PENDING |
| H6 | Graceful AI error fallback | Fake LLM returning 500 | `tracecase analyze tc.json --provider openai --base-url http://127.0.0.1:9100/v1` | Falls back to heuristic, labels source as "heuristic" | Subprocess Pytest | PENDING |
| H7 | Structure of `analysis.json` | Valid analysis | Check output keys | Contains `summary`, `risk_score`, `risks`, `recommended_assertions`, `negative_proposals` | Subprocess Pytest | PENDING |
| H8 | Heuristic trigger rules | Bad form / 500 error | Analyze test with unvalidated form / network 500 | Flags form submission without validation, 500 error | Subprocess Pytest | PENDING |
| H9 | Malformed base-url diagnostic | None | `tracecase analyze tc.json --base-url "bad_url"` | Clear error message, no crash | Subprocess Pytest | PENDING |

---

### Section I: Corpus (Index/Search/Coverage/Clean/MCP)
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| I1 | Index test directory | Testcase directory | `tracecase index ./recordings --db ./test_corpus.db` | Indexes all testcases into SQLite FTS5 | Subprocess Pytest / Hand-written | PENDING |
| I2 | Custom DB path | None | `tracecase index ./recordings --db ./custom.db` | Creates custom DB | Subprocess Pytest | PENDING |
| I3 | Re-index with `--clear` | Existing index | `tracecase index ./recordings --db ./test_corpus.db --clear` | Drops and rebuilds tables | Subprocess Pytest | PENDING |
| I4 | Idempotency of indexing | Existing index | `tracecase index ./recordings --db ./test_corpus.db` twice | No duplicate entries, count remains identical | Subprocess Pytest | PENDING |
| I5 | BM25 search term ranking | Indexed corpus | `tracecase search "login" --db ./test_corpus.db` | Returns BM25-ranked results with highlighted snippets | Subprocess Pytest / Hand-written | PENDING |
| I6 | Search limit flag | Indexed corpus | `tracecase search "button" --limit 2 --db ./test_corpus.db` | Returns at most 2 results | Subprocess Pytest | PENDING |
| I7 | Search by selector / URL / text | Indexed corpus | Search by `input[name='email']`, URL, button text | Matches appropriate testcases | Subprocess Pytest | PENDING |
| I8 | Search with no results | Indexed corpus | `tracecase search "nonexistent_term_xyz"` | Reports 0 matches cleanly | Subprocess Pytest | PENDING |
| I9 | Special characters in search | Indexed corpus | Search `""`, `AND`, `OR`, `*`, `NOT` | FTS5 syntax handled without SQLite exception | Subprocess Pytest | PENDING |
| I10 | Coverage report CLI | Indexed corpus | `tracecase coverage --db ./test_corpus.db` | Displays covered domains, endpoints, actions table | Subprocess Pytest | PENDING |
| I11 | Duplicate-flow warning | Identical testcases | Run `tracecase coverage` on duplicated flows | Emits duplicate warning | Subprocess Pytest | PENDING |
| I12 | Coverage on empty / missing DB | Nonexistent DB | `tracecase coverage --db ./empty.db` | Reports 0 testcases gracefully | Subprocess Pytest | PENDING |
| I13 | `tracecase clean --db` | Corpus DB exists | `tracecase clean --db --db-path ./test_corpus.db` | Deletes SQLite DB | Subprocess Pytest | PENDING |
| I14 | `tracecase clean --all` | Isolated workspace | `tracecase clean --all --db-path ./test_corpus.db` | Cleans DB and recording directories | Subprocess Pytest | PENDING |
| I15 | `tracecase clean` flags combo | Isolated workspace | Test `--recordings`, `--no-db` | Selectively deletes only specified targets | Subprocess Pytest | PENDING |
| I16 | Bare `tracecase clean` defaults | Corpus DB exists | `tracecase clean --db-path ./test_corpus.db` | Defaults to wiping DB while preserving recordings | Subprocess Pytest | PENDING |
| I17 | MCP server initialize | MCP server | Send JSON-RPC `initialize` over stdio | Responds with protocolVersion and tools capability | MCP Client / Pytest | PENDING |
| I18 | MCP tool: `search_testcases` | Indexed corpus | Call `search_testcases` with query | Returns JSON list of matches | MCP Client / Pytest | PENDING |
| I19 | MCP tool: `get_testcase` | Valid & invalid ID | Call `get_testcase` with valid ID and unknown ID | Valid returns full JSON; unknown returns error | MCP Client / Pytest | PENDING |
| I20 | MCP tool: `coverage_report` vs `get_coverage` | Indexed corpus | Call `coverage_report` and `get_coverage` | `coverage_report` succeeds; `get_coverage` raises method not found | MCP Client / Pytest | PENDING |
| I21 | MCP custom DB path | Custom DB | `tracecase mcp --db ./custom.db` | Reads from specified custom DB | MCP Client / Pytest | PENDING |
| I22 | MCP stdout purity | MCP running | Send invalid requests | No raw text or logging printed to stdout (protocol purity) | MCP Client / Pytest | PENDING |

---

### Section J: Regression and CI Intelligence
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| J1 | `tracecase changes` | Git fixture repo | `tracecase changes --base HEAD~1 --target HEAD` | Outputs detected file diffs, routes, selectors | Subprocess Pytest | PENDING |
| J2 | `tracecase map` | Git repo + tests | `tracecase map --repo ./fixture_repo` | Maps testcases to application routes and selectors | Subprocess Pytest | PENDING |
| J3 | `tracecase impact` | Git repo with diff | `tracecase impact --base HEAD~1 --target HEAD` | Outputs impacted testcases with confidence scores | Subprocess Pytest | PENDING |
| J4 | `tracecase risk` | Git repo | `tracecase risk --base HEAD~1 --target HEAD` | Evaluates predictive risk score per testcase | Subprocess Pytest | PENDING |
| J5 | `tracecase select` strategies | Impacted tests | Test strategies: `highest_risk`, `time_budget`, `balanced` | Selects optimal test subset honoring constraints | Subprocess Pytest | PENDING |
| J6 | `tracecase explain` | Prior selection ID | `tracecase explain <selection_id>` | Explains why each test was selected or excluded | Subprocess Pytest | PENDING |
| J7 | `tracecase report` formats | Selection ID | `tracecase report <id> --format markdown` and `--format json_manifest` | Generates formatted report or manifest | Subprocess Pytest | PENDING |
| J8 | `tracecase run` selection | Git repo | `tracecase run --strategy time_budget --time-budget 60` | Executes selected tests | Subprocess Pytest | PENDING |
| J9 | `tracecase ci` standard gate | Git repo | `tracecase ci --base HEAD~1 --gate standard` | Evaluates CI Quality Gate | Subprocess Pytest | PENDING |
| J10 | `tracecase ci` matrix & concurrency | Git repo | `tracecase ci --concurrency 2 --browser chromium` | Runs concurrent CI execution | Subprocess Pytest | PENDING |
| J11 | CI baseline drift & pre-existing | Fixture repo | Test with pre-existing failure vs new regression | Pre-existing tolerated if allowed; new regression fails gate | Subprocess Pytest | PENDING |
| J12 | `tracecase ci-upload` | SUT running | Upload CI manifest to SUT via `ci-upload` | Manifest ingested and visible in Studio | Subprocess Pytest | PENDING |
| J13 | `tracecase benchmark` | Test suite | `tracecase benchmark --iterations 2 --suite all` | Reports sequential vs parallel vs pooled metrics | Subprocess Pytest | PENDING |
| J14 | `tracecase storage` inspection | Studio workspace | `tracecase storage` | Reports artifact sizes, DB size, screenshot bytes | Subprocess Pytest | PENDING |
| J15 | `tracecase storage --dry-run` | Execution artifacts | `tracecase storage --prune --dry-run` | Shows what would be deleted without disk modification | Subprocess Pytest | PENDING |
| J16 | `tracecase storage` retention rules | Artifacts > 7 days | `tracecase storage --older-than 7d --keep-latest 5 --apply` | Prunes artifacts older than 7d while keeping 5 latest | Subprocess Pytest | PENDING |
| J17 | `tracecase storage --failures-only` | Passed and failed runs | `tracecase storage --failures-only --apply` | Retains failed runs, prunes passing runs | Subprocess Pytest | PENDING |
| J18 | Git error handling | Non-git directory | `tracecase changes --repo /tmp` | Clear error: "Not a git repository" | Subprocess Pytest | PENDING |
| J19 | `tracecase ci` report outputs | CI run | Check `--junit`, `--sarif`, `--report`, `--manifest` | Generates valid JUnit XML, SARIF, Markdown, JSON | Subprocess Pytest | PENDING |
| J20 | `tracecase ci` config file | YAML config | `tracecase ci --config tracecase.yaml` | Reads settings from YAML config file | Subprocess Pytest | PENDING |

---

### Section K: Studio: Launch and Server
| ID | Title | Preconditions | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| K1 | Launch UI default | Clean workspace | `tracecase ui --no-browser` | Server starts on 127.0.0.1:8000, returns HTML | Subprocess Pytest / Hand-written | PENDING |
| K2 | Custom port option | Port 8088 free | `tracecase ui --port 8088 --no-browser` | Listens on port 8088 | Subprocess Pytest | PENDING |
| K3 | `--no-browser` flag | Default | `tracecase ui --no-browser` | Does not attempt `webbrowser.open()` | Subprocess Pytest | PENDING |
| K4 | Host binding option | None | `tracecase ui --host 127.0.0.1` | Binds strictly to specified host interface | Subprocess Pytest | PENDING |
| K5 | Port collision error | Port in use | Start two UI servers on same port | Second server exits with port in use error | Subprocess Pytest | PENDING |
| K6 | Static UI missing fallback | Empty static dir | Access `/` when static dir absent | Returns "Static UI not found" fallback HTML | HTTP Client / Pytest | PENDING |
| K7 | Clean SIGINT / SIGTERM shutdown | Running UI | Send SIGINT to server process | Shuts down orchestrator and exits 0 | Subprocess Pytest | PENDING |
| K8 | `studio.db` initialization & persistence | Fresh workspace | Launch UI, create item, restart UI | DB created in `.tracecase/studio.db` and persists data | Subprocess Pytest | PENDING |
| K9 | OpenAPI schema & API sanity | Running UI | `GET /openapi.json` | Returns valid OpenAPI 3.1.0 schema | HTTP Client / Pytest | PENDING |
| K10 | JSON error responses | Running UI | `GET /api/nonexistent` | Returns JSON error `{"detail": "..."}`, never raw HTML 500 | HTTP Client / Pytest | PENDING |

---

### Section L: Studio Modules (Golden Path, Empty State, Error State)
| ID | Title | Module / Page | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| L0 | Navigation & Theme | Global Sidebar | Deep link each route, toggle dark/light theme | Routes render without JS error, theme persists | Dogfood Recording / Playwright | PENDING |
| L1 | Overview Dashboard | Overview (`/`) | Inspect KPI counters and charts | Reflects real counts of testcases, runs, pass rate | Dogfood Recording / Playwright | PENDING |
| L2 | Projects Management | Projects (`/projects`) | Create project, rename, duplicate name, delete | CRUD works, prevents duplicate IDs | Dogfood Recording / Playwright | PENDING |
| L3 | Test Cases Explorer | Testcases (`/testcases`) | Search/filter, open detail, view steps/logs | Steps and screenshots render cleanly | Dogfood Recording / Playwright | PENDING |
| L4 | Test Suites Manager | Suites (`/suites`) | Create suite, add tests, reorder, delete | Suite associations updated in DB | Dogfood Recording / Playwright | PENDING |
| L5 | Browser Recorder | Recorder (`/recorder`) | Launch recording session, pause, resume, stop | Session recorded, testcase created in DB | Dogfood Recording / Hand-written | PENDING |
| L6 | Test Executions Replay | Executions (`/executions`) | Execute single run, batch run, matrix run, cancel | Live execution logs stream via WebSocket | Dogfood Recording / Hand-written | PENDING |
| L7 | Execution History | History (`/history`) | Filter past runs, inspect step failure, healed badge | Step drilldown shows error and healed locator | Dogfood Recording / Playwright | PENDING |
| L8 | Reports Generation | Reports (`/reports`) | Generate HTML/Markdown report, download | Report rendered and downloadable | Dogfood Recording / Playwright | PENDING |
| L9 | Visual Regression Diff | Visual (`/visual-diff`) | Select two screenshots, inspect overlay diff | Visual overlay and diff percentage rendered | Dogfood Recording / Playwright | PENDING |
| L10 | CI Quality Gate Dashboard | CI Dashboard (`/ci`) | View CI runs, inspect gate verdict and baseline drift | Drift records and gate status displayed | Dogfood Recording / Playwright | PENDING |
| L11 | Smart Regression Selection | Smart Reg (`/regression-selection`) | Compute regression set with Time Budget 120s | Selected test list with duration and reasons | Dogfood Recording / Playwright | PENDING |
| L12 | Autonomous Exploration | Explore (`/explore`) | Crawl URL with depth 2, render graph, synthesize | Navigation graph rendered, draft synthesized | Dogfood Recording / Playwright | PENDING |
| L13 | Requirements Planner | Planner (`/explore`) | Input user story -> Map & Plan Test -> review queue | Provenance evidence rendered, approve draft | Dogfood Recording / Playwright | PENDING |
| L14 | AI Test Assistant | Assistant (`/ai-assistant`) | Ask question with Fake LLM / Provider Null | Returns context-grounded response or graceful offline msg | Dogfood Recording / Playwright | PENDING |
| L15 | Test Analysis & Healing Audit | Analysis (`/test-analysis`) | Suggest Assertions, Audit Selectors, Risk Audit | Fragile selectors flagged, assertions suggested | Dogfood Recording / Hand-written | PENDING |
| L16 | Negative Test Generation | Mutations (`/mutations`) | Select test -> Synthesize Negative Tests | Variations listed, replay triggered from UI | Dogfood Recording / Playwright | PENDING |
| L17 | Test Repository Search | Repository (`/repository`) | Full-text search by selector, reindex | BM25 snippets rendered, reindex updates store | Dogfood Recording / Playwright | PENDING |
| L18 | Code Generator UI | Codegen (`/codegen`) | Select test -> view Playwright code -> Copy | Code rendered with copy feedback | Dogfood Recording / Playwright | PENDING |
| L19 | Network Inspector | Network (`/network`) | Inspect requests per test, filter by status | Headers, timing, request/response bodies rendered | Dogfood Recording / Playwright | PENDING |
| L20 | MCP Integrations Guide | MCP (`/mcp`) | View config snippet, copy Claude Desktop config | Valid JSON config copied | Dogfood Recording / Playwright | PENDING |
| L21 | Studio Settings | Settings (`/settings`) | Update browser, AI provider, API key, save | Settings persist in `app_settings` across reload | Dogfood Recording / Hand-written | PENDING |
| L22 | Storage Management | Storage (`/storage`) | View usage metrics, execute prune with confirmation | Disk usage updated after prune | Dogfood Recording / Playwright | PENDING |
| L23 | Testcase Flakiness Analysis | Flakiness API | View flakiness metrics on testcase detail | Flakiness score and retry history calculated | Dogfood Recording / Playwright | PENDING |
| L24 | Journey Draft Versioning & Diff | Explore Drafts | Create draft version 2 -> diff versions | Snapshot diff rendered showing added/removed steps | Dogfood Recording / Playwright | PENDING |
| L25 | Live Selector Verification | Analysis API | Verify selector live against running browser | Returns match count and visibility status | Dogfood Recording / Playwright | PENDING |
| L26 | Batch & Matrix Cancellation | Executions API | Start batch -> click Cancel | All queued runs transition to cancelled | Dogfood Recording / Playwright | PENDING |

---

### Section M: Cross-Cutting Concerns
| ID | Title | Scope | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| M1 | Privacy: Provider Null | Network isolation | Run analyze and assistant with `provider: null` | Zero outbound internet or LLM network packets | Network Monitor / Pytest | PENDING |
| M2 | Privacy: Metadata Audit | Fake LLM | Inspect payload sent to Fake LLM on 9100 | Verifies only allowed step metadata sent, no raw secrets | Fake LLM Server Log | PENDING |
| M3 | Provenance Labeling | AI & Analysis | Verify tags on suggested assertions & drafts | Explicitly marked "heuristic" or "llm_generated" | Subprocess Pytest | PENDING |
| M4 | Hostile Data Escaping | HTML/XSS Safety | Record inputs with `<img src=x onerror=...>` | Studio UI and HTML report escape tags safely | Playwright XSS Audit | PENDING |
| M5 | Large Recording Scalability | Performance | Generate testcase with 500 steps & 1MB bodies | UI loads without freeze, CLI completes in reasonable time | Stress Test / Pytest | PENDING |
| M6 | Cross-Platform Paths | Path handling | Test POSIX vs Windows-style paths | Resolves cleanly across platforms | Unit / Subprocess Pytest | PENDING |
| M7 | Concurrency Isolation | Studio backend | Concurrently trigger record + replay | Operations execute independently without deadlock | Asyncio Pytest | PENDING |
| M8 | Path Traversal Protection | File endpoints | `GET /api/testcases/../../../etc/passwd` | 400 or 404 returned, path traversal blocked | HTTP Security Pytest | PENDING |

---

### Section N: End-to-End Journeys
| ID | Title | Description | Steps | Expected Result | Method | Status |
|---|---|---|---|---|---|---|
| N1 | Full QA Engineer Lifecycle | Record to Pytest to Index | Record -> Replay -> Analyze -> Attach Assertions -> Codegen -> Pytest -> Index -> Search -> Coverage | Complete pipeline succeeds, pytest passes | E2E Pytest Journey | PENDING |
| N2 | Mutation & Robustness | Record to Mutation to Studio | Record -> Mutate -> Replay all mutations -> Inspect in Studio | Identifies regressions in negative variations | E2E Pytest Journey | PENDING |
| N3 | Offline API Mocking | Record to HAR to Offline Replay | Record with API -> Export HAR -> Stop backend -> Replay with HAR | Passes completely offline | E2E Pytest Journey | PENDING |
| N4 | Visual Drift & Self-Healing | A to B to C Evolution | Record on Ver-A -> Replay Ver-B (--heal) -> Visual Diff Ver-C | Heals locators on B, detects visual drift on C | E2E Pytest Journey | PENDING |
| N5 | CLI & Studio Interoperability | Bidirectional sync | CLI-recorded test appears in Studio; Studio-recorded test replayed from CLI | Full compatibility | E2E Pytest Journey | PENDING |
| N6 | Autonomous Journey Synthesis | Exploration to Approved Test | Crawl site -> Synthesize Journey -> Approve Draft -> Replay -> Codegen | Generates approved executable test from crawler | E2E Pytest Journey | PENDING |
| N7 | Git Change to CI Gate | Impacted CI validation | Commit git change -> impact -> select -> ci gate -> report -> ci-upload to Studio | Shows in Studio CI Quality Gate | E2E Pytest Journey | PENDING |
| N8 | DEMO_GUIDE 20-min Walkthrough | Complete Demo Validation | Execute DEMO_GUIDE.md verbatim step-by-step | Matches documented script, logs any behavioral variance | E2E Pytest Journey | PENDING |
