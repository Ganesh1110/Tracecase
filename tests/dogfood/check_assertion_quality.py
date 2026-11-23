#!/usr/bin/env python3
"""AST-based assertion-quality linter for dogfood tests.

Flags weak tests:
1. Functions with no assert statements.
2. Functions that assert ONLY on process returncode.
3. Assertions using `assert True` or bare truthiness of objects.
4. CLI execution tests that only check `res.stdout` with `in` but never check file contents.
"""

import ast
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).resolve().parent / "cli_tests"


class AssertionQualityVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[dict[str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        if not node.name.startswith("test_"):
            return

        assert_nodes: list[ast.Assert] = [
            n for n in ast.walk(node) if isinstance(n, ast.Assert)
        ]
        # Also recognize pytest.raises in with blocks
        has_pytest_raises = False
        for with_node in [n for n in ast.walk(node) if isinstance(n, ast.With)]:
            for item in with_node.items:
                if isinstance(item.context_expr, ast.Call):
                    func_str = ast.unparse(item.context_expr.func)
                    if "raises" in func_str:
                        has_pytest_raises = True

        if not assert_nodes and not has_pytest_raises:
            self.violations.append({
                "file": self.filename,
                "func": node.name,
                "line": str(node.lineno),
                "rule": "NO_ASSERT",
                "message": "Test function contains zero assert statements or pytest.raises blocks.",
            })
            return

        # Check for assert True or bare constants
        for a in assert_nodes:
            if isinstance(a.test, ast.Constant) and a.test.value is True:
                self.violations.append({
                    "file": self.filename,
                    "func": node.name,
                    "line": str(a.lineno),
                    "rule": "ASSERT_TRUE",
                    "message": "Useless `assert True` found.",
                })

        # Check if ALL asserts only check returncode
        returncode_asserts = 0
        for a in assert_nodes:
            # Look for attribute returncode
            attrs = [
                n.attr for n in ast.walk(a.test) if isinstance(n, ast.Attribute)
            ]
            if "returncode" in attrs and len(attrs) == 1:
                returncode_asserts += 1

        if returncode_asserts == len(assert_nodes):
            self.violations.append({
                "file": self.filename,
                "func": node.name,
                "line": str(node.lineno),
                "rule": "ONLY_RETURNCODE",
                "message": "Test only asserts on process returncode without checking state, stdout, or artifacts.",
            })

        # Check for commands generating files where only stdout is checked with `in`
        has_file_write_flag = False
        checks_file_content = False
        has_stdout_in_check = False

        for call in ast.walk(node):
            if isinstance(call, ast.Call):
                # Check for run_tracecase calls
                call_name = ""
                if isinstance(call.func, ast.Name):
                    call_name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    call_name = call.func.attr

                if call_name in ("run_tracecase", "run"):
                    # Check if -o or --output is in args
                    for arg in call.args:
                        if isinstance(arg, ast.List):
                            for elt in arg.elts:
                                if isinstance(elt, ast.Constant) and str(elt.value) in ("-o", "--output"):
                                    has_file_write_flag = True

                # Check if test reads files or parses json
                if call_name in ("read_text", "read_bytes", "loads", "model_validate_json"):
                    checks_file_content = True

        for a in assert_nodes:
            for cmp in ast.walk(a):
                if isinstance(cmp, ast.Compare):
                    for op in cmp.ops:
                        if isinstance(op, ast.In):
                            # Check if stdout is checked
                            attrs = [n.attr for n in ast.walk(cmp) if isinstance(n, ast.Attribute)]
                            if "stdout" in attrs or "stderr" in attrs:
                                has_stdout_in_check = True

        is_failure_expectation = False
        for a in assert_nodes:
            if isinstance(a.test, ast.Compare):
                for op in a.test.ops:
                    if isinstance(op, ast.NotEq):
                        attrs = [n.attr for n in ast.walk(a.test) if isinstance(n, ast.Attribute)]
                        if "returncode" in attrs:
                            is_failure_expectation = True

        if has_file_write_flag and has_stdout_in_check and not checks_file_content and not is_failure_expectation:
            self.violations.append({
                "file": self.filename,
                "func": node.name,
                "line": str(node.lineno),
                "rule": "STDOUT_ONLY_FILE_UNCHECKED",
                "message": "Command passes -o/--output but test only asserts stdout without checking produced file content.",
            })


def run_linter() -> int:
    all_violations = []
    py_files = sorted(TARGET_DIR.glob("test_*.py"))
    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            visitor = AssertionQualityVisitor(py_file.name)
            visitor.visit(tree)
            all_violations.extend(visitor.violations)
        except Exception as e:
            print(f"Error parsing {py_file}: {e}")
            return 1

    print("=" * 80)
    print("ASSERTION QUALITY LINTER REPORT")
    print("=" * 80)
    if not all_violations:
        print(f"✓ All tests in {len(py_files)} test files passed quality assertion linting!")
        print("  - Zero functions without assert")
        print("  - Zero returncode-only asserts")
        print("  - Zero bare assert True statements")
        print("  - All artifact-producing commands verify file contents")
        return 0

    print(f"Found {len(all_violations)} assertion quality violations:\n")
    for v in all_violations:
        print(f"  [{v['rule']}] {v['file']}:{v['line']} in {v['func']}(): {v['message']}")

    return 1


if __name__ == "__main__":
    sys.exit(run_linter())
