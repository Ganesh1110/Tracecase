"""Git Fixture Repo Builder for Tracecase dogfooding.

Builds an isolated temporary git repository with 3+ commits touching routes,
selectors, and symbols to test:
- `tracecase changes`
- `tracecase map`
- `tracecase impact`
- `tracecase risk`
- `tracecase select`
- `tracecase ci`
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def build_git_fixture_repo(target_dir: Path | str) -> dict[str, str]:
    """Create a git fixture repo with 3 commits and return commit hashes."""
    repo = Path(target_dir).resolve()
    repo.mkdir(parents=True, exist_ok=True)

    def run_git(*args: str) -> str:
        cmd = ["git"] + list(args)
        res = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=True)
        return res.stdout.strip()

    # Git init with default main branch
    run_git("init", "-b", "main")
    run_git("config", "user.name", "Tracecase Dogfood")
    run_git("config", "user.email", "dogfood@tracecase.local")

    src_dir = repo / "src"
    src_dir.mkdir(exist_ok=True)

    # --- Commit 1: Initial Baseline ---
    (src_dir / "routes.py").write_text(
        'ROUTES = ["/login", "/dashboard", "/checkout"]\n'
        'def login(): return "login page"\n'
        'def checkout(): return "checkout page"\n',
        encoding="utf-8",
    )
    (src_dir / "components.jsx").write_text(
        'export const LoginButton = () => <button id="btn-login" className="btn-primary">Sign In</button>;\n'
        'export const CheckoutButton = () => <button id="btn-checkout">Checkout</button>;\n',
        encoding="utf-8",
    )
    run_git("add", ".")
    run_git("commit", "-m", "commit 1: initial baseline routes and selectors")
    commit_1 = run_git("rev-parse", "HEAD")

    # --- Commit 2: Modify login selector & checkout route ---
    (src_dir / "components.jsx").write_text(
        '// Changed selector ID from btn-login to btn-signin\n'
        'export const LoginButton = () => <button id="btn-signin" className="btn-modern">Sign In</button>;\n'
        'export const CheckoutButton = () => <button id="btn-checkout">Checkout</button>;\n',
        encoding="utf-8",
    )
    (src_dir / "routes.py").write_text(
        'ROUTES = ["/login", "/dashboard", "/checkout", "/cart"]\n'
        'def login(): return "login page updated"\n'
        'def checkout(): return "checkout page"\n',
        encoding="utf-8",
    )
    run_git("add", ".")
    run_git("commit", "-m", "commit 2: update login selector and add cart route")
    commit_2 = run_git("rev-parse", "HEAD")

    # --- Commit 3: Add profile route & critical payment change ---
    (src_dir / "routes.py").write_text(
        'ROUTES = ["/login", "/dashboard", "/checkout", "/cart", "/profile"]\n'
        'def login(): return "login page updated"\n'
        'def checkout(): return "checkout page secure"\n'
        'def profile(): return "user profile"\n',
        encoding="utf-8",
    )
    (src_dir / "payment.py").write_text(
        'class PaymentGateway:\n'
        '    def process(self, amount):\n'
        '        return {"status": "success", "amount": amount}\n',
        encoding="utf-8",
    )
    run_git("add", ".")
    run_git("commit", "-m", "commit 3: add profile route and payment gateway")
    commit_3 = run_git("rev-parse", "HEAD")

    return {
        "repo_path": str(repo),
        "commit_1": commit_1,
        "commit_2": commit_2,
        "commit_3": commit_3,
        "base_ref": commit_1,
        "target_ref": commit_3,
    }


if __name__ == "__main__":
    import tempfile
    tmp = tempfile.mkdtemp(prefix="tc_git_fixture_")
    info = build_git_fixture_repo(tmp)
    print("Git fixture created successfully at:", info["repo_path"])
    print("Commits:", info["commit_1"][:8], "->", info["commit_2"][:8], "->", info["commit_3"][:8])
