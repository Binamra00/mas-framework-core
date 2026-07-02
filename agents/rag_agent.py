# agents/rag_agent.py
import os
import chromadb
from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from rich.console import Console


console = Console()

# --- PATH FIX ---
FRAMEWORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_CHROMA_PATH = os.path.join(FRAMEWORK_ROOT, 'memory', 'chroma_db')
# ----------------

# --- RAG confidence gate ----------------------------------------------------
# ChromaDB distance above which an architectural-pattern match is too weak to
# propose. This is the `refactoring_guru_patterns` collection — its distance
# scale is DIFFERENT from the IntentScout taxonomy, so calibrate it on its OWN
# good/bad matches (the 1.70 Flyweight "match" for a file-loading task is the
# kind of noise this is meant to silence). PRELIMINARY value — tune empirically.
RAG_CONFIDENCE_THRESHOLD = 1.0


class RagRetrievalAgent(BaseAgent):
    """
    Tier 1: Queries the local ChromaDB vector store to fetch
    Refactoring Guru rules using semantic search.
    """

    def __init__(self, db_path: str = DEFAULT_CHROMA_PATH):
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_collection(name="refactoring_guru_patterns")

    def execute(self, blackboard: ContextBlackboard) -> None:
        # 1. The Semantic Short-Circuit
        if getattr(blackboard, 'intent_nature', None) in ["COSMETIC", "CHURN"]:
            console.print(rf"\[RagAgent] Task is {blackboard.intent_nature}. Bypassing architectural context retrieval.")
            return

        console.print(r"\[RagAgent] Querying vector database for architectural context...")

        query_text = f"{blackboard.target_file} {blackboard.task_description}"

        results = self.collection.query(
            query_texts=[query_text],
            n_results=1,
            include=["documents", "metadatas", "distances"]
        )

        if results and results['documents'] and results['documents'][0]:
            matched_rule = results['documents'][0][0]
            matched_metadata = results['metadatas'][0][0]
            distance = results['distances'][0][0]

            pattern_name = matched_metadata.get('name', 'Unknown Pattern')
            pattern_intent = matched_metadata.get('intent', 'No description available.')
            short_intent = pattern_intent.split('.')[0] + '.' if '.' in pattern_intent else pattern_intent

            # 2. Confidence gate: don't cry wolf on weak matches.
            # Transparent (not silent): we report the weak match and how to force it.
            if distance > RAG_CONFIDENCE_THRESHOLD:
                console.print(
                    rf"\[RagAgent] No high-confidence architectural pattern found "
                    rf"(closest: '{pattern_name}', distance {distance:.2f} > {RAG_CONFIDENCE_THRESHOLD:.2f}). Skipping.")
                console.print(
                    "[dim]  ↳ Re-run with an explicit pattern name if you intended to enforce one.[/dim]")
                return

            # 3. Progressive-disclosure HITL verification (confident match only)
            console.print(
                rf"[bold cyan]\[RagAgent] Architectural Proposal[/bold cyan] [dim](Vector Distance: {distance:.2f})[/dim]")
            console.print(f"The AI detected a potential architectural requirement: [bold]'{pattern_name}'[/bold]")
            console.print(f"  [dim]• What it is:[/dim] {short_intent}")
            console.print(
                "  [dim]• Impact:[/dim] If enforced, the AI will aggressively restructure the generated code to adhere to this GoF pattern.")
            console.print(
                r"[bold yellow]  \[WARNING] Only enforce this if your team explicitly uses this pattern here. If unsure, safely skip.[/bold yellow]")

            while True:
                choice = input(
                    f"Do you want to enforce the '{pattern_name}' design constraint? [y/N]: ").strip().lower()
                if choice == 'y':
                    formatted_rule = f"[{pattern_name} Pattern] {matched_rule}"
                    if not hasattr(blackboard, 'rag_context'):
                        blackboard.rag_context = []
                    blackboard.rag_context.append(formatted_rule)
                    console.print(f"[bold green]↳ Injected '{pattern_name}' into JIT context.[/bold green]")
                    break
                elif choice in ('n', ''):
                    console.print("[bold green]↳ Architectural injection bypassed by user.[/bold green]")
                    break
                else:
                    console.print("Invalid input. Please enter 'y' or 'n'.")