# agents/triage_agent.py
import math
import re
import json

from chromadb.utils import embedding_functions

from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.llm_providers import LLMProvider
from core.ast_slicer import ASTSlicer
from rich.console import Console

console = Console()

# --- Relevance escalation: rank-based, NOT a correctness threshold ----------
# Selecting an entity outside the top-N ranked matches triggers a heads-up —
# never a block, never a verdict. Scale-free, no correctness implication.
# Sensitivity dial only; bump it or move it to palace.yaml per project.
RELEVANCE_TOP_N = 2


class TriageAgent(BaseAgent):
    """
    Tier 3.5: The Routing Agent.
    Slices the target file, maps the prompt to candidate entities, surfaces an
    independent embedding-relevance ranking, and — when the prompt names a kind
    of logic but no entity — runs a logic locator that reads the actual code to
    report which entities contain that logic. Every lock passes through HITL.
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._ef = None  # lazy embedder

    # --- Embedding-relevance machinery -------------------------------------
    def _embedder(self):
        if self._ef is None:
            self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        return self._ef

    @staticmethod
    def _cosine(a, b) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def _rank_entities(self, task: str, entities: dict, metadata: dict) -> dict:
        """{entity: cosine_similarity_to_task}. Fail-soft -> {}."""
        try:
            names = list(entities.keys())
            docs = []
            for n in names:
                meta = metadata.get(n, {})
                docs.append(f"{n}\n{meta.get('signature', '')}\n{meta.get('docstring', '')}\n{entities[n]}")
            ef = self._embedder()
            texts = [task] + docs
            try:
                vectors = ef(input=texts)
            except TypeError:
                vectors = ef(texts)
            task_vec = vectors[0]
            return {names[i]: self._cosine(task_vec, vectors[i + 1]) for i in range(len(names))}
        except Exception as e:
            console.print(f"[dim][TriageAgent] Relevance ranking unavailable ({e}); proceeding without it.[/dim]")
            return {}

    # --- Logic locator (reads actual code; advisory, dev still picks) -------
    def _locate_logic(self, task: str, entities: dict) -> dict:
        """Ask the LLM which entities actually CONTAIN logic matching the request.
        Returns {entity: short_reason}. Fail-soft -> {}. Advisory only — the
        developer makes the final selection (HITL)."""
        try:
            listing = "\n\n".join(f"### {name}\n{code}" for name, code in entities.items())
            prompt = (
                "A developer wants to perform a refactoring but did NOT name a target method:\n"
                f"REQUEST: '{task}'\n\n"
                "Below are the file's entities. Identify ONLY the entities that actually CONTAIN logic "
                "matching the request (e.g. for 'file loading logic', entities that open/read files). "
                "For each, give a SHORT reason naming the specific behavior that matches.\n"
                "Return STRICT JSON: a list of {\"entity\": \"<exact name>\", \"reason\": \"<short>\"}. "
                "If none clearly match, return [].\n"
                "Do not include entities that lack the requested logic. No prose, no code fences.\n\n"
                f"ENTITIES:\n{listing}"
            )
            raw = self.provider.generate_code(prompt).strip()
            raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw).strip()
            data = json.loads(raw)
            located = {}
            for item in data:
                ent = str(item.get("entity", "")).strip()
                if ent in entities:
                    located[ent] = str(item.get("reason", "")).strip()
            return located
        except Exception as e:
            console.print(f"[dim][TriageAgent] Logic locator unavailable ({e}); showing full target list.[/dim]")
            return {}

    # --- Shared review + HITL chokepoint -----------------------------------
    def _review_targets(self, selected_targets: list, metadata: dict, relevance: dict, located: dict) -> str:
        console.print(
            f"\n[bold yellow][TriageAgent] Target tentatively selected: {', '.join(selected_targets)}[/bold yellow]")

        for target in selected_targets:
            target_meta = metadata.get(target, {})
            console.print(f"[bold magenta][Preview: {target}][/bold magenta]")
            console.print(f"  • Signature: {target_meta.get('signature', 'Unknown')}")
            raw_doc = target_meta.get('docstring', 'No docstring provided.')
            short_doc = " ".join(raw_doc.splitlines())[:150] + ("..." if len(raw_doc) > 150 else "")
            console.print(f"  • Docstring: {short_doc}")
            console.print(f"  • Size: {target_meta.get('size', '0')} lines of code")
            if relevance:
                console.print(f"  • Task relevance: [bold]{relevance.get(target, 0.0):.3f}[/bold]")
            if target in located:
                console.print(f"  • [green]Located logic:[/green] {located[target]}")

        # Rank-based escalation — skipped for entities the locator verified.
        low_conf = []
        top_names = []
        if relevance:
            ranked = sorted(relevance.items(), key=lambda kv: kv[1], reverse=True)
            top_names = [n for n, _ in ranked[:RELEVANCE_TOP_N]]
            if len(ranked) > RELEVANCE_TOP_N:
                low_conf = [t for t in selected_targets if t not in top_names and t not in located]

        if low_conf:
            suggestions = [n for n in top_names if n not in selected_targets]
            console.print(
                f"\n[bold red][Zero-Trust Verify][/bold red] "
                f"'{', '.join(low_conf)}' is not among the top {RELEVANCE_TOP_N} relevance matches for this request.")
            if suggestions:
                console.print(f"[yellow]Higher-ranked candidates: {', '.join(suggestions)}.[/yellow]")
            console.print("[dim]This is a heads-up, not a verdict — verify where the logic actually sits.[/dim]")
            while True:
                choice = input(
                    "\n[p]roceed anyway / [s]elect a different target / [a]bort and re-run: ").strip().lower()
                if choice == 'p':
                    return 'confirm'
                elif choice == 's':
                    return 'reselect'
                elif choice in ('a', ''):
                    return 'abort'
                console.print("Invalid input. Enter 'p', 's', or 'a'.")

        confirm = input("\nDoes this look like the correct logic to modify? [Y/n]: ").strip().lower()
        return 'confirm' if confirm in ('y', '') else 'reselect'

    # --- Interactive selection (TUI) ---------------------------------------
    def _prompt_user_for_entity(self, blackboard: ContextBlackboard, entity_names: list,
                                metadata: dict, relevance: dict, located: dict):
        """Returns the selected target list, or None if the developer aborts."""
        console.print(
            f"\n[bold yellow][TriageAgent] Target is ambiguous. File contains {len(entity_names)} entities.[/bold yellow]")

        if blackboard.progressive_context:
            console.print("\n[bold blue][Palace] Recent Activity on this file:[/bold blue]")
            for item in blackboard.progressive_context:
                console.print(f"  • {item}")

        if located:
            console.print("\n[bold green]The AI located the requested logic in these entities:[/bold green]")
            for name, reason in located.items():
                console.print(f"  • [bold]{name}[/bold] — {reason}")
            console.print("[dim]These are listed first below. You may pick one of them, or any other target.[/dim]")

        def order(names):
            # Located entities first, then by relevance (best-first), else AST order.
            def key(n):
                return (0 if n in located else 1,
                        -(relevance.get(n, 0.0) if relevance else 0.0))
            return sorted(names, key=key)

        filtered_names = order(entity_names)

        while True:
            if len(filtered_names) <= 15:
                header = "\n[bold cyan]Available Targets[/bold cyan]"
                header += " [dim](located logic first, then by relevance)[/dim]:" if (located or relevance) else ":"
                console.print(header)
                for i, name in enumerate(filtered_names):
                    tag = " [green]\\[contains logic][/green]" if name in located else ""
                    if relevance:
                        console.print(f"  [{i + 1}] {name}  [dim](relevance {relevance.get(name, 0.0):.3f})[/dim]{tag}")
                    else:
                        console.print(f"  [{i + 1}] {name}{tag}")

                choice = input("\nSelect target(s) (e.g., '1' or '2,3') OR type text to filter: ").strip()
                if not choice:
                    continue

                if all(part.strip().isdigit() for part in choice.split(',')):
                    indices = [int(p.strip()) - 1 for p in choice.split(',')]
                    if all(0 <= idx < len(filtered_names) for idx in indices):
                        selected_targets = [filtered_names[idx] for idx in indices]
                        decision = self._review_targets(selected_targets, metadata, relevance, located)
                        if decision == 'confirm':
                            return selected_targets
                        elif decision == 'abort':
                            return None
                        else:
                            console.print("[red]Selection cancelled. Please select again.[/red]\n")
                            filtered_names = order(entity_names)
                            continue
                    console.print("[red]One or more invalid number selections.[/red]")
                    continue
            else:
                console.print(f"\n[dim]List too long to display ({len(filtered_names)} items).[/dim]")
                choice = input("Type a keyword to filter entities (e.g., 'process' or 'init'): ").strip()
                if not choice:
                    continue

            if not all(part.strip().isdigit() for part in choice.split(',')):
                new_filtered = order([name for name in filtered_names if choice.lower() in name.lower()])
                if not new_filtered:
                    console.print(f"[bold red]No entities match '{choice}'. Resetting list.[/bold red]")
                    filtered_names = order(entity_names)
                else:
                    filtered_names = new_filtered
                    console.print(f"[green]Filtered down to {len(filtered_names)} results.[/green]")

    # --- Pipeline entry ----------------------------------------------------
    def execute(self, blackboard: ContextBlackboard) -> None:
        console.print("\n[bold magenta][TriageAgent][/bold magenta] Slicing file and determining target entity...")

        try:
            sliced_data = ASTSlicer.slice_file(blackboard.target_file)
            entities = sliced_data['entities']
            metadata = sliced_data.get('metadata', {})
            entity_names = list(entities.keys())
        except Exception as e:
            console.print(f"[bold red][TriageAgent] AST Parsing Failed: {e}[/bold red]")
            return

        if not entity_names:
            console.print("[yellow][TriageAgent] No distinct methods found. Defaulting to full-file payload.[/yellow]")
            return

        relevance = self._rank_entities(blackboard.task_description, entities, metadata)
        located = {}  # locator output, carried to the Inspector for an intent advisory

        triage_prompt = (
                "You are a strict routing system. Match the user's modification request to the exact target method name.\n\n"
                f"User Request: '{blackboard.task_description}'\n\n"
                "Available Targets:\n" + "\n".join([f"- {name}" for name in entity_names]) + "\n\n"
                "CRITICAL RULES:\n"
                "1. ONLY return a target name if the user EXPLICITLY names it in their request OR if the request uniquely applies to ONLY one specific method.\n"
                "2. If the request is generic (e.g., 'Add a comment', 'Clean up') or refers to multiple areas, return EXACTLY 'AMBIGUOUS'.\n"
                "3. You are strictly forbidden from guessing. If unsure, return 'AMBIGUOUS'.\n"
                "4. Do NOT wrap your answer in backticks."
        )

        try:
            raw_response = self.provider.generate_code(triage_prompt).strip()
            matched_entities = []

            if "AMBIGUOUS" in raw_response.upper():
                # Prompt named a kind of logic but no entity -> locate it in the code.
                located.update(self._locate_logic(blackboard.task_description, entities))
                matched_entities = self._prompt_user_for_entity(
                    blackboard, entity_names, metadata, relevance, located)
            else:
                direct = next((e for e in entity_names if e == raw_response), None)
                if direct is None:
                    console.print(
                        "[bold yellow][TriageAgent] Model gave invalid or fuzzy target. Falling back to TUI.[/bold yellow]")
                    located.update(self._locate_logic(blackboard.task_description, entities))
                    matched_entities = self._prompt_user_for_entity(
                        blackboard, entity_names, metadata, relevance, located)
                else:
                    decision = self._review_targets([direct], metadata, relevance, {})
                    if decision == 'confirm':
                        matched_entities = [direct]
                    elif decision == 'reselect':
                        located.update(self._locate_logic(blackboard.task_description, entities))
                        matched_entities = self._prompt_user_for_entity(
                            blackboard, entity_names, metadata, relevance, located)
                    else:
                        matched_entities = None

            if not matched_entities:
                console.print("[bold red][TriageAgent] Aborted. Re-run with the verified target.[/bold red]")
                return

            target_names_str = ", ".join(matched_entities)
            console.print(f"[bold green][TriageAgent] Target(s) locked: {target_names_str}[/bold green]")

            blackboard.target_entity_name = target_names_str
            blackboard.target_entity_code = "\n\n".join([entities[name] for name in matched_entities])

            # Carry the locator's finding so the Inspector can raise an intent
            # advisory (NOT a block) if a locked target lacks the requested logic.
            blackboard.located_logic = located
            blackboard.targets_missing_logic = [t for t in matched_entities if located and t not in located]

        except Exception as e:
            console.print(f"[bold red][TriageAgent] Triage API Error: {e}[/bold red]")