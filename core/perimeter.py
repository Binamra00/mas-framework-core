# core/perimeter.py
"""Single source of truth for the MAS Zero-Trust traversal perimeter.

Every filesystem walk in the framework — file resolution (cli.py), DOM scanning
(dom_scanner.py), and any future agent that touches the tree — MUST go through
these helpers. This guarantees the ignore policy can never drift between
subsystems again (the bug where resolve_target_file and RepoDOMScanner kept two
separate, diverging ignore lists).

Design note: these are SECURITY-RELEVANT defaults, hardcoded on purpose. Config
(e.g. palace.yaml) may EXTEND the ignore set via extend_ignores(), but can never
shrink the hardcoded floor — so a missing or malformed config can never silently
disable the perimeter.
"""
from __future__ import annotations

import os
from typing import Iterable

# --- Hardcoded floor: directories never descended into ---------------------
IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",                                  # VCS
    "venv", ".venv", "env", ".env",                         # virtual environments
    "site-packages", "node_modules", "vendor",              # vendored dependencies
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", "build", "dist", ".eggs",                     # build artifacts
    ".idea", ".vscode",                                     # IDE metadata
    ".mas_chroma",                                          # MAS internal vector store
})

# --- Whitelist of extensions treated as editable source --------------------
VALID_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py",                                                  # Python
    ".java", ".kt", ".scala",                               # JVM
    ".js", ".ts", ".jsx", ".tsx",                           # Web / JS
    ".c", ".cpp", ".h", ".hpp", ".cs",                      # C-family
    ".go", ".rs", ".rb", ".php",                            # Others
})

# --- Compiled/binary artifacts that must never enter LLM context -----------
BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".class", ".pyc", ".pyo", ".exe", ".dll", ".so", ".o", ".a", ".jar", ".war",
})

# Project-specific additions (populated at startup from config, optional).
_EXTRA_IGNORES: set[str] = set()


def extend_ignores(names: Iterable[str]) -> None:
    """Add project-specific ignore dirs (e.g. from palace.yaml's `ignore_dirs`).

    Can only ADD to the perimeter; the hardcoded IGNORE_DIRS floor is immutable,
    so config can tighten the boundary but never weaken it.
    """
    for name in names or ():
        if name and name.strip():
            _EXTRA_IGNORES.add(name.strip())


def is_ignored_dir(name: str) -> bool:
    """A directory is skipped if it's hidden (dotfile) or in the ignore set."""
    return name.startswith(".") or name in IGNORE_DIRS or name in _EXTRA_IGNORES


def prune_dirs(dirs: list[str]) -> None:
    """In-place prune of os.walk's `dirs` list. Requires a top-down walk
    (os.walk's default), since mutation only steers traversal top-down.

        for root, dirs, files in os.walk(root_dir):
            perimeter.prune_dirs(dirs)
            ...
    """
    dirs[:] = [d for d in dirs if not is_ignored_dir(d)]


def is_source_file(filename: str) -> bool:
    """True only for non-hidden files carrying a whitelisted source extension."""
    if filename.startswith("."):
        return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in VALID_SOURCE_EXTENSIONS


def is_binary_file(filename: str) -> bool:
    """True for compiled/binary artifacts that must be kept out of context."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in BINARY_EXTENSIONS