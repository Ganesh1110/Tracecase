# Tracecase Execution Performance Benchmark

**Environment:** Python Playwright | Concurrency: 3 | Workload: 6 executions per paradigm

| Metric | Sequential Cold | Parallel Cold | Parallel Pooled (Tracecase) |
| :--- | :---: | :---: | :---: |
| **Wall-Clock Time** | 1.18s | 0.76s | **0.46s** |
| **Throughput** | 304.4 tests/min | 471.1 tests/min | **790.6 tests/min** |
| **Browser Startup (Cold)** | 108.1 ms | 220.1 ms | 262.8 ms |
| **Warm Context Allocation** | N/A (cold) | N/A (cold) | **33.2 ms** |
| **Execution Duration (P50)** | 48.7 ms | 74.6 ms | **75.2 ms** |
| **Execution Duration (P95)** | 55.8 ms | 75.2 ms | **75.9 ms** |
| **Peak Runner RSS** | 59.5 MB | 60.2 MB | **60.9 MB** |

### Key Improvements
- **Warm Context Overhead Reduction:** **69.3%** faster allocation vs cold process launch.
- **Wall-Clock Speedup:** **2.60x** vs sequential cold, **1.68x** vs parallel cold.
