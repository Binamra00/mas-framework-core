# agents/inspector_agent.py
import os
import ast
import difflib
import yaml
import json
import tempfile
import webbrowser
from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.llm_providers import LLMProvider

from rich.console import Console

console = Console()


class InspectorAgent(BaseAgent):
    """
    Tier 5: The Quality Assurance Agent.
    Structural smells (scope / God Agent, syntax validity) are checked
    DETERMINISTICALLY via AST diff — same verdict every run. The LLM grader is
    reserved for genuinely semantic smells (Context Bleed, Prompt Drift, Lazy
    Regex). It is a GRADER, not a coder — it emits a verdict only, never code.
    """

    def __init__(self, provider: LLMProvider, project_root: str):
        self.provider = provider
        self.smells_path = os.path.join(project_root, "config", "smells.yaml")
        self.policy_path = os.path.join(project_root, "config", "refactoring_rules.json")
        self._catalog = None

    # --- Smell descriptions (single source of truth: smells.yaml) -----------
    def _smell_catalog(self) -> dict:
        if self._catalog is not None:
            return self._catalog
        catalog = {
            # Built-in fallbacks for smells not defined in smells.yaml.
            "Invalid Python": "The patch does not parse as valid Python — applying it would break the file.",
            "AST Violation": "The patch satisfied a structural request by editing only strings, comments, or "
                             "docstrings instead of real code (lazy regex-style replacement).",
            "Lazy Regex Replacement": "The patch changed only string literals / comments / docstrings to satisfy a "
                                      "request that required actual structural code changes.",
        }
        try:
            if os.path.exists(self.smells_path):
                with open(self.smells_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}
                for s in cfg.get('agentic_smells', []):
                    if s.get('name'):
                        catalog[s['name']] = s.get('description', '')
        except Exception:
            pass
        self._catalog = catalog
        return catalog

    def _describe_smell(self, name: str) -> str:
        catalog = self._smell_catalog()
        if name in catalog:
            return catalog[name]
        for key, desc in catalog.items():               # substring match
            if key.lower() in name.lower():
                return desc
        return ""

    def _block(self, smell_name: str, details: str = "") -> None:
        console.print(f"\n[bold red]BLOCK! Agentic Smell Detected:[/bold red] [bold]{smell_name}[/bold]")
        desc = self._describe_smell(smell_name)
        if desc:
            console.print(f"  [dim]↳ What this means:[/dim] {desc}")
        if details:
            console.print(f"  [dim]↳ Details:[/dim] {details}")
        console.print("[yellow]The patch has been intercepted and discarded.[/yellow]")

    # --- Deterministic structural checks (AST) ------------------------------
    @staticmethod
    def _function_units(source: str) -> dict:
        """Map function/method qualified-name -> structural signature (ast.dump,
        no positions), matching ASTSlicer naming ('name' / 'Class.method').
        ast.dump ignores whitespace/formatting but captures logic + docstrings,
        so a function that merely MOVED reads as unchanged."""
        tree = ast.parse(source)
        units = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                units[node.name] = ast.dump(node)
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        units[f"{node.name}.{child.name}"] = ast.dump(child)
        return units

    def _ast_scope_violations(self, original_source: str, proposed_units: dict, locked_str: str) -> list:
        """Return non-target function/method units that were modified or removed.
        Newly-added units (extraction helpers) are allowed; the locked target is
        allowed. Everything else changing = scope creep (God Agent)."""
        try:
            orig_units = self._function_units(original_source)
        except SyntaxError:
            return []  # can't compare safely; don't raise a false positive

        locked = {n.strip() for n in (locked_str or "").split(",") if n.strip()}
        locked_simple = {n.split(".")[-1] for n in locked}

        out = []
        for name in set(orig_units) | set(proposed_units):
            simple = name.split(".")[-1]
            allowed = name in locked or simple in locked_simple
            in_o = name in orig_units
            in_n = name in proposed_units
            if in_o and in_n and orig_units[name] != proposed_units[name] and not allowed:
                out.append(name)
            elif in_o and not in_n and not allowed:
                out.append(f"{name} (removed)")
        return out

    # --- Pipeline entry ----------------------------------------------------
    def execute(self, blackboard: ContextBlackboard) -> None:
        if not blackboard.proposed_new_code:
            return  # Coding Agent failed to generate anything

        console.print("\n[bold magenta][InspectorAgent][/bold magenta] Evaluating patch against Agentic Smells...")

        original = blackboard.original_file_content or ""
        proposed = blackboard.proposed_new_code
        target = getattr(blackboard, "target_entity_name", "") or ""
        intent_nature = getattr(blackboard, "intent_nature", "UNKNOWN").upper()

        # --- Deterministic Gate 1: syntax validity ---
        try:
            proposed_units = self._function_units(proposed)
        except SyntaxError as e:
            self._block("Invalid Python", f"{e}")
            return

        # --- Deterministic Gate 2: scope / God Agent ---
        violations = self._ast_scope_violations(original, proposed_units, target)
        if violations:
            self._block(
                "God Agent Violation",
                f"Changed code outside your locked target ('{target}'): {', '.join(violations)}. "
                f"Only the target may be modified (plus any newly-extracted helper).")
            return

        # --- LLM Gate: semantic smells ONLY (scope handled above) ---
        policy_text = "No specific safety policy defined."
        if os.path.exists(self.policy_path):
            with open(self.policy_path, 'r', encoding='utf-8') as f:
                try:
                    policy_text = json.dumps(json.load(f), indent=2)
                except json.JSONDecodeError:
                    policy_text = "Error parsing safety policy JSON."

        grading_prompt = (
            "You are a code quality inspector. SCOPE / God-Agent violations are checked separately and "
            "deterministically — do NOT evaluate scope, line counts, or how many methods changed.\n\n"
            "Evaluate ONLY these smells:\n"
            "- Context Bleed: the patch references imports, variables, or symbols never present in the original file.\n"
            "- Prompt Drift: the code is valid but its logic drifted from the user's actual request.\n"
            "- Lazy Regex Replacement (ONLY if intent is NOT CHURN): a structural request was satisfied by editing "
            "only string literals, comments, or docstrings instead of real code.\n\n"
            f"SAFETY POLICY:\n{policy_text}\n\n"
            f"NATURE OF INTENT: {intent_nature}\n"
            f"USER REQUEST: {blackboard.task_description}\n\n"
            f"ORIGINAL CODE:\n```python\n{original}\n```\n\n"
            f"PROPOSED CODE:\n```python\n{proposed}\n```\n\n"
            "OUTPUT FORMAT (STRICT — you are a grader, not a coder):\n"
            "- Respond with EXACTLY 'PASS', or 'FAIL: <smell name> - <one short sentence>'.\n"
            "- NEVER output corrected code, code blocks, file contents, or fixes. Only the verdict line.\n"
        )

        # The LLM grader is ADVISORY, not a block: these are judgment-based,
        # non-deterministic smells. We surface them; the human decides at the diff.
        advisories = []

        grade = self.provider.generate_code(grading_prompt).strip()
        no_code = grade.split("```")[0].strip()
        verdict_line = next((ln.strip() for ln in no_code.splitlines() if ln.strip()), "")

        if verdict_line.upper().startswith("FAIL"):
            after = verdict_line.split("FAIL:", 1)[-1].strip() if "FAIL:" in verdict_line else verdict_line
            smell_name = after.split(" - ")[0].split(" – ")[0].strip() or "Quality Concern"
            detail = after[len(smell_name):].lstrip(" -–:").strip()
            desc = self._describe_smell(smell_name)
            msg = f"[bold]{smell_name}[/bold]"
            if desc:
                msg += f" — {desc}"
            if detail:
                msg += f" ({detail})"
            advisories.append(msg)

        # Locator-based intent advisory (reuses the Triage locator output; no new LLM call):
        # if a locked target lacked the requested logic, the patch may not do what was asked.
        missing = getattr(blackboard, "targets_missing_logic", []) or []
        located = getattr(blackboard, "located_logic", {}) or {}
        if missing:
            where = ", ".join(located.keys()) if located else "other entities"
            advisories.append(
                f"[bold]Intent mismatch[/bold] — the locator did not find your requested logic in "
                f"'{', '.join(missing)}'. It was located in: {where}. The patch may implement something "
                f"other than what you asked.")

        console.print("[bold green][InspectorAgent] Structural checks passed (scope + syntax).[/bold green]")
        self._show_diff_and_prompt(blackboard, advisories)

    def _show_diff_and_prompt(self, blackboard: ContextBlackboard, advisories=None) -> None:
        diff = list(difflib.unified_diff(
            blackboard.original_file_content.splitlines(keepends=True),
            blackboard.proposed_new_code.splitlines(keepends=True),
            fromfile=f"Original: {blackboard.target_file}",
            tofile=f"Generated: {blackboard.target_file}",
            n=3
        ))

        if not diff:
            return

        html_content = "<html style='background: #1e1e1e; color: #d4d4d4; font-family: monospace; padding: 20px;'>"
        html_content += f"<h2>Proposed Patch: {blackboard.target_file}</h2><pre style='font-size: 14px; line-height: 1.5;'>"
        for line in diff:
            escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if line.startswith('+') and not line.startswith('+++'):
                html_content += f"<span style='color: #4CAF50;'>{escaped}</span>"
            elif line.startswith('-') and not line.startswith('---'):
                html_content += f"<span style='color: #F44336;'>{escaped}</span>"
            elif line.startswith('@@'):
                html_content += f"<span style='color: #00BCD4;'>{escaped}</span>"
            else:
                html_content += escaped
        html_content += "</pre></html>"

        fd, path = tempfile.mkstemp(suffix=".html", prefix="mas_diff_")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_content)

        console.print(f"\n[bold cyan][InspectorAgent][/bold cyan] Patch generated. Opening diff viewer in browser...")
        webbrowser.open(f"file://{path}")

        if advisories:
            console.print("\n[bold yellow]\u26a0 Advisories — review the diff carefully before accepting:[/bold yellow]")
            for a in advisories:
                console.print(f"  \u2022 {a}")

        while True:
            choice = input("\nExecute Patch? [a]ccept / [r]eject / [m] save draft: ").strip().lower()
            if choice == 'a':
                with open(blackboard.target_file, "w", encoding="utf-8") as f:
                    f.write(blackboard.proposed_new_code)
                console.print(f"[bold green]Success![/bold green] '{blackboard.target_file}' patched surgically.")
                blackboard.patch_successful = True
                break
            elif choice == 'r':
                console.print("[bold red]Patch rejected.[/bold red] File left untouched.")
                break
            elif choice == 'm':
                draft = blackboard.target_file + ".mas-draft"
                with open(draft, "w", encoding="utf-8") as f:
                    f.write(blackboard.proposed_new_code)
                console.print(f"[bold yellow]Draft saved to '{draft}'.[/bold yellow]")
                break
            else:
                print("Invalid choice.")