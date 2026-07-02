# core/dom_scanner.py
import os
import re
import hashlib
import sqlite3
from typing import Dict, List

from core import perimeter

# Back-compat re-export: existing `from core.dom_scanner import VALID_SOURCE_EXTENSIONS`
# call sites keep working, but the canonical definition now lives in perimeter.
VALID_SOURCE_EXTENSIONS = perimeter.VALID_SOURCE_EXTENSIONS


class RepoDOMScanner:
    """
    The Tier 3 retrieval engine. Maps the repository, resolves dependencies
    via imports, and extracts token-efficient structural signatures.
    Leverages Lazy SQLite caching for O(1) lookups on unchanged files.
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.dom_map: Dict[str, str] = {}
        self.db_path = os.path.join(root_dir, ".mas_palace.db")

    def _compute_hash(self, filepath: str) -> str:
        """Returns the SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                buf = f.read()
                hasher.update(buf)
            return hasher.hexdigest()
        except FileNotFoundError:
            return None

    def build_dom(self) -> None:
        """Fast O(N) alias mapping. Does not read file contents."""
        for root, dirs, files in os.walk(self.root_dir):
            # Single source of truth: identical pruning to file resolution.
            perimeter.prune_dirs(dirs)
            for file in files:
                # is_source_file enforces both the hidden-file rule and the
                # whitelist, so binaries (.pyc/.class) and dotfiles can't leak in.
                if perimeter.is_source_file(file):
                    alias = os.path.splitext(file)[0]
                    self.dom_map[alias] = os.path.join(root, file)

    def resolve_downstream_dependencies(self, target_file: str) -> List[str]:
        dependencies = []
        if not os.path.exists(target_file):
            return dependencies

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract Java files: "import com.enterprise.api.TransactionDTO;" -> "TransactionDTO"
        java_imports = re.findall(r'import\s+[\w\.]+\.(\w+);', content)

        # Extract Python modules: "from core.blackboard import Context" -> "core.blackboard" -> "blackboard"
        py_modules = re.findall(r'from\s+([\w\.]+)\s+import', content)
        py_imports = [m.split('.')[-1] for m in py_modules]

        # Extract Python direct imports: "import core.dom_scanner" -> "dom_scanner"
        py_direct = re.findall(r'^import\s+([\w\.]+)', content, re.MULTILINE)
        py_imports += [m.split('.')[-1] for m in py_direct]

        aliases = set(java_imports + py_imports)

        for alias in aliases:
            if alias in self.dom_map:
                dependencies.append(self.dom_map[alias])

        return dependencies

    def structural_grep(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return ""

        current_hash = self._compute_hash(file_path)

        # --- 1. Check Cache First (O(1) Lookup) ---
        if os.path.exists(self.db_path) and current_hash:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT file_hash, signatures FROM dom_cache WHERE filepath = ?", (file_path,))
                    row = cursor.fetchone()
                    if row and row[0] == current_hash:
                        return row[1]  # Cache Hit!
            except sqlite3.OperationalError:
                pass  # Failsafe if the cli.py hasn't created the table yet

        # --- 2. Cache Miss: Expensive File Parsing ---
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        signature_lines = []
        brace_depth = 0

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("package ") or stripped.startswith("import ") or stripped.startswith("from "):
                signature_lines.append(line.rstrip())
                continue

            open_braces = stripped.count('{')
            close_braces = stripped.count('}')

            if brace_depth == 0 and stripped:
                if not stripped.startswith("//") and not stripped.startswith("/*") and not stripped.startswith("#"):
                    signature_lines.append(line.rstrip())
                    if open_braces > close_braces or stripped.endswith(":"):
                        signature_lines.append("        // ... implementation hidden ...")

            brace_depth += (open_braces - close_braces)

            if brace_depth == 0 and close_braces > open_braces:
                signature_lines.append("}")

        final_signature = "\n".join(signature_lines)

        # --- 3. Save to Cache ---
        if os.path.exists(self.db_path) and current_hash:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR REPLACE INTO dom_cache (filepath, file_hash, signatures) VALUES (?, ?, ?)",
                        (file_path, current_hash, final_signature))
            except sqlite3.OperationalError:
                pass

        return final_signature