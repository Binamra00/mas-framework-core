# agents/coding_agent.py
import os
import difflib
import re

from core import blackboard
from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.llm_providers import LLMProvider
from core.patch_engine import PatchEngine

from rich.console import Console
from rich.text import Text

console = Console()


class UniversalCodingAgent(BaseAgent):
    """
    Tier 4: The Execution Agent.
    Executes a surgical strike using JIT isolated context and strict Patch formatting.
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def _show_diff_and_prompt(self, blackboard: ContextBlackboard, target_file: str, original_code: str,
                              new_code: str) -> bool:
        diff = list(difflib.unified_diff(
            original_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile=f"Original: {target_file}",
            tofile=f"Generated: {target_file}",
            n=3
        ))

        if not diff:
            console.print("\n[bold yellow]No structural changes were made.[/bold yellow]")
            return False

        console.print("\n[bold cyan]--- SURGICAL PATCH PROPOSED ---[/bold cyan]")
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                console.print(Text(line, style="green"), end="")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(Text(line, style="red"), end="")
            elif line.startswith("@@"):
                console.print(Text(line, style="cyan"), end="")
            else:
                console.print(line, end="")
        console.print("\n[bold cyan]---------------------------------[/bold cyan]")

        while True:
            console.print("\n[bold]Execute Patch?[/bold]")
            console.print("  [[green]a[/green]] Accept and overwrite file")
            console.print("  [[red]r[/red]] Reject patch")
            console.print("  [[yellow]m[/yellow]] Manual merge (Saves draft)")

            choice = input("\nChoice (a/r/m): ").strip().lower()

            if choice == 'a':
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(new_code)
                console.print(f"[bold green]Success![/bold green] '{target_file}' patched surgically.")
                blackboard.patch_successful = True
                return True
            elif choice == 'r':
                console.print("[bold red]Patch rejected.[/bold red] File left untouched.")
                return False
            elif choice == 'm':
                draft_path = target_file + ".mas-draft"
                with open(draft_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
                console.print(f"[bold yellow]Draft saved to '{draft_path}'.[/bold yellow]")
                return True
            else:
                print("Invalid choice.")

    def execute(self, blackboard: ContextBlackboard) -> None:
        console.print("\n[bold magenta][CodingAgent][/bold magenta] Engaging Surgical Patch Engine...")

        # If Triage failed to isolate an entity, we fallback to the whole file
        target_context = blackboard.target_entity_code if blackboard.target_entity_code else blackboard.compile_payload()

        # --- SCOPE FIX ---
        # history_str stays optional, but constraint_str, guardrail_instructions, and
        # patch_prompt MUST always be defined. Previously these were nested inside the
        # `if blackboard.progressive_context:` block, so any file with no history crashed
        # with UnboundLocalError at `len(patch_prompt)` below.

        # Compile progressive history (optional)
        history_str = ""
        if blackboard.progressive_context:
            history_str = "Recent Actions on this file (For Context):\n" + "\n".join(
                [f"- {p}" for p in blackboard.progressive_context]) + "\n\n"

        # Compile taxonomy execution constraint (always evaluated)
        constraint_str = ""
        if getattr(blackboard, "taxonomy_id", None) and getattr(blackboard, "execution_constraint", None):
            constraint_str = (
                f"TAXONOMY CLASSIFICATION: {blackboard.taxonomy_id}\n"
                f"EXECUTION CONSTRAINT: {blackboard.execution_constraint}\n"
                "You MUST obey this structural constraint during generation.\n\n"
            )

        # The Paranoia Override (Context Mismatch Guardrail)
        if getattr(blackboard, "intent_nature", None) == "CHURN":
            guardrail_instructions = (
                "1. CONTEXT MISMATCH GUARDRAIL: BYPASSED. This is a CHURN/DOCUMENTATION request.\n"
                "2. You MUST apply the requested formatting or comments to the Target Code regardless of semantic relevance. Do NOT abort.\n"
            )
        else:
            guardrail_instructions = (
                "1. CONTEXT MISMATCH GUARDRAIL: You must first analyze if the specific semantic domain of the request (e.g., 'database', 'auth', 'UI') is actually present in the Target Code.\n"
                "2. If the requested domain logic is MISSING, do NOT generalize or extract unrelated code. You MUST stop and output EXACTLY: <<<<<<< ABORT: Context Mismatch >>>>>>>\n"
            )

        # Build the strict patching prompt with Chain-of-Thought Guardrails.
        # --- MULTI-BLOCK FIX ---
        # The engine now parses and applies multiple SEARCH/REPLACE blocks, so the
        # instructions ask for ONE block per modified method instead of an impossible
        # "single consecutive block" spanning non-adjacent functions.
        patch_prompt = (
            "You are a precision code patcher. Your task is to modify the provided code according to the user's request.\n\n"
            f"{history_str}"
            f"User Request: {blackboard.task_description}\n\n"
            f"{constraint_str}"
            f"Target Code Entity:\n```python\n{target_context}\n```\n\n"
            "CRITICAL OUTPUT RULES:\n"
            f"{guardrail_instructions}"
            "3. If the logic IS present (or the guardrail is bypassed), output one or more strict SEARCH/REPLACE blocks.\n"
            "4. Each SEARCH block MUST perfectly match the existing code, including exact indentation and whitespace.\n"
            "5. If you modify MULTIPLE methods, emit a SEPARATE SEARCH/REPLACE block for EACH one. NEVER span unrelated or non-adjacent methods inside a single block.\n"
            "6. Keep every SEARCH block as small as possible. For example, when inserting a docstring, the SEARCH block can be just the signature line.\n"
            "7. Output ONLY the analysis line and the blocks. Format each block exactly like this, separated by a blank line:\n\n"
            "Analysis: [Your 1-sentence analysis of whether the request applies to the code]\n"
            "<<<<<<< SEARCH\n"
            "def first_method(self):\n"
            "=======\n"
            "def first_method(self):\n"
            '    """Docstring for the first method."""\n'
            ">>>>>>> REPLACE\n\n"
            "<<<<<<< SEARCH\n"
            "def second_method(self):\n"
            "=======\n"
            "def second_method(self):\n"
            '    """Docstring for the second method."""\n'
            ">>>>>>> REPLACE\n"
        )

        # Token Profiler
        char_count = len(patch_prompt)
        approx_tokens = char_count // 4
        console.print(
            f"[bold cyan][Diagnostic] Surgical Payload: {char_count} chars (≈ {approx_tokens} tokens)[/bold cyan]")

        try:
            with open(blackboard.target_file, "r", encoding="utf-8") as f:
                original_file_content = f.read()

            raw_response = self.provider.generate_code(patch_prompt)

            # --- LAYER 2: INTERCEPT ABORT SIGNAL BEFORE PARSING ---
            if "<<<<<<< ABORT: Context Mismatch >>>>>>>" in raw_response:
                # Optionally print the LLM's reasoning for the abort
                analysis_match = re.search(r'Analysis:\s*(.*)', raw_response)
                reason = analysis_match.group(1) if analysis_match else "No reasoning provided."
                raise ValueError(
                    f"Context Mismatch: The AI determined the requested logic is missing.\n[AI Reasoning]: {reason}")

            # --- MULTI-BLOCK FIX ---
            # extract_blocks now returns a list of (search, replace) pairs;
            # apply_patch applies them sequentially.
            blocks = PatchEngine.extract_blocks(raw_response)
            final_file_content = PatchEngine.apply_patch(original_file_content, blocks)

            # Save state to blackboard for the Inspector Agent
            blackboard.original_file_content = original_file_content
            blackboard.proposed_new_code = final_file_content

        except Exception as e:
            error_msg = str(e)

            # Translate internal PatchEngine mechanics into User-Friendly UX
            if "SEARCH block" in error_msg or "exactly match" in error_msg:
                console.print("\n[bold red][Scope Boundary Violation][/bold red]")
                console.print("The AI attempted to modify logic that is outside the scope of your selected target.")
                console.print("[dim]Hint: Ensure your prompt strictly applies to the method/entity you selected, not the whole file.[/dim]")
            else:
                console.print(f"\n[bold red][CodingAgent] Patch Execution Error:[/bold red] {error_msg}")

            blackboard.errors.append(error_msg)