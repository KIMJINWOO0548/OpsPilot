"""Exercise the extracted source package's required-file check."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def source_package(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package = tmp_path / "source"
    shutil.copytree(
        root, package,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
            "node_modules", ".local", "build", "dist", "*.egg-info",
        ),
    )
    return package


def run_check(package, cwd):
    return subprocess.run(
        [sys.executable, str(package / "scripts/check_package.py")],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8",
    )


def test_complete_source_package_can_be_checked_from_another_directory(source_package, tmp_path):
    result = run_check(source_package, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("required", ["START_HERE.md", "AGENTS.md"])
def test_source_package_rejects_missing_development_or_safety_guide(
    source_package, tmp_path, required,
):
    (source_package / required).unlink(missing_ok=True)
    result = run_check(source_package, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert required in result.stdout
