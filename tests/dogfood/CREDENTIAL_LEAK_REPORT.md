| Surface | Password Canary (`CANARY_PW_9f3a7c`) | API Key Canary (`CANARY_API_KEY_8a2d1e`) | Severity | Leak Detected? |
|---|---|---|---|---|
| `testcase.json` | **LEAKED** | **LEAKED** | CRITICAL (BUG-009) | ⚠️ **YES** |
| `testcase.md` | **LEAKED** | **LEAKED** | CRITICAL (BUG-009) | ⚠️ **YES** |
| `testcase.html` | **LEAKED** | **LEAKED** | CRITICAL (BUG-009) | ⚠️ **YES** |
| `screenshots` | Clean | Clean | LOW | ✅ None |
| `.har export` | **LEAKED** | Clean | CRITICAL (BUG-009) | ⚠️ **YES** |
| `generated pytest` | Clean | **LEAKED** | MED (Design Decision) | ⚠️ **YES** |
| `mutations/*.json` | **LEAKED** | **LEAKED** | CRITICAL (BUG-009) | ⚠️ **YES** |
| `analysis.json` | Clean | Clean | LOW | ✅ None |
| `replay.json` | Clean | Clean | LOW | ✅ None |
| `corpus.db (FTS)` | Clean | Clean | LOW | ✅ None |
| `CLI stdout/stderr` | Clean | Clean | LOW | ✅ None |
| `MCP responses` | **LEAKED** | **LEAKED** | CRITICAL (BUG-009) | ⚠️ **YES** |
| `Fake-LLM logs` | Clean | Clean | LOW | ✅ None |
