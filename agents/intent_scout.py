# agents/intent_scout.py
import os
import yaml
import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console

from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.llm_providers import LLMProvider

console = Console()


class IntentScoutAgent(BaseAgent):
    """
    Tier 0: The Intent Classifier.
    Uses local vector search to deterministically map a user's natural language
    prompt to a specific RefactoringMiner taxonomy rule before any code is written.
    """

    def __init__(self, provider: LLMProvider, project_root: str):
        self.provider = provider
        self.project_root = project_root
        self.taxonomy_path = os.path.join(project_root, "config", "refactoring_taxonomy.yaml")
        # Store the vector DB locally in the project root alongside the SQLite DB
        self.chroma_db_path = os.path.join(project_root, ".mas_chroma")

        # Initialize the local embedding model
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

    def _ingest_taxonomy(self, collection) -> bool:
        """Reads the YAML and populates the vector store if empty or outdated."""
        if not os.path.exists(self.taxonomy_path):
            console.print(f"[bold red][IntentScout] Taxonomy file not found at {self.taxonomy_path}[/bold red]")
            return False

        with open(self.taxonomy_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("taxonomy", [])
        if not rules:
            return False

        # JIT Check: If the DB count matches the YAML count, skip ingestion
        if collection.count() == len(rules):
            return True

        console.print("[dim][IntentScout] Initializing Taxonomy Vector Store (First run only)...[/dim]")

        documents = []
        metadatas = []
        ids = []

        for rule in rules:
            # We embed both the name and intent for the highest semantic match probability
            documents.append(f"{rule['name']}: {rule['intent']}")
            metadatas.append({
                "name": rule["name"],
                "category": rule["category"],
                "nature": rule["nature"],
                "safety_level": rule["safety_level"],
                "execution_constraint": rule["execution_constraint"],
                "multi_file": str(rule["multi_file"]).lower()
            })
            ids.append(rule["id"])

        # Upsert the entire taxonomy into ChromaDB
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        return True

    def execute(self, blackboard: ContextBlackboard) -> None:
        console.print("\n[bold cyan][IntentScout][/bold cyan] Analyzing prompt to classify operation intent...")

        # --- INPUT SMELL LINTER (Quad-State God Prompt, Vague Prompt, & Churn Detection) ---
        linter_prompt = (
            "You are a Zero-Trust Prompt Linter. Evaluate the developer's refactoring prompt and return a JSON object with 'status' and 'reason'.\n\n"
            f"USER PROMPT: \"{blackboard.task_description}\"\n\n"
            "RULES:\n"
            "1. STATUS: \"REJECT\" - Use ONLY if the prompt explicitly demands MULTIPLE distinct refactoring rules (e.g., \"extract this method AND rename the variable\"). The system strictly supports ONE rule at a time.\n"
            "2. STATUS: \"WARNING\" - Use if the prompt is vague, generalized, or lacks specific instruction (e.g., \"make it better\", \"optimize the database\").\n"
            "3. STATUS: \"CHURN\" - Use ONLY if the prompt exclusively requests adding comments, docstrings, formatting, or removing whitespace without changing ANY executable logic (e.g., \"add docstrings\", \"format the file\").\n"
            "4. STATUS: \"PASS\" - Use if the prompt is a clear, single-responsibility structural, cosmetic, or behavioral refactoring intent.\n\n"
            "Output strictly in JSON format: {\"status\": \"PASS|WARNING|CHURN|REJECT\", \"reason\": \"Explanation here\"}"
        )

        response = self.provider.generate_code(linter_prompt).strip()

        # Clean up potential markdown formatting from LLM response
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            import json
            linter_result = json.loads(response)
            status = linter_result.get("status", "PASS")
            reason = linter_result.get("reason", "")
        except Exception:
            status = "PASS"  # Fallback to pass if parsing fails

        if status == "REJECT":
            console.print("\n[bold red][Input Smell Detected] God Prompt Rejected[/bold red]")
            console.print("[red]Zero-Trust Policy: You may only execute ONE refactoring rule at a time.[/red]")
            console.print(f"[yellow]Reason: {reason}[/yellow]")
            import sys
            sys.exit(0)

        elif status == "WARNING":
            # ... (Keep your existing Consultant Hard Stop block here) ...
            console.print("\n[bold yellow][Input Smell Detected] Vague Prompt Warning[/bold yellow]")
            console.print("[yellow]Zero-Trust Warning: The AI might hallucinate based on this vague instruction.[/yellow]")
            console.print("\n[cyan]Consulting Taxonomy for Potential Matches...[/cyan]")
            try:
                client = chromadb.PersistentClient(path=self.chroma_db_path)
                collection = client.get_or_create_collection(name="refactoring_taxonomy", embedding_function=self.ef)
                self._ingest_taxonomy(collection)
                results = collection.query(
                    query_texts=[blackboard.task_description],
                    n_results=3,
                    include=["metadatas"]
                )
                console.print("[bold]To proceed safely, please run `mas refactor` again and explicitly request one of the following operations:[/bold]")
                for idx, meta in enumerate(results['metadatas'][0]):
                    console.print(f"  {idx + 1}. [bold cyan]{meta['name']}[/bold cyan] (Nature: {meta['nature']})")
            except Exception:
                console.print("[dim]Unable to fetch taxonomy suggestions.[/dim]")
            console.print("\n[red]Execution Aborted: Please refine your prompt to match a single, explicit refactoring rule.[/red]")
            import sys
            sys.exit(0)

        elif status == "CHURN":
            console.print("\n[bold green][Input Smell Detected] Pure Documentation/Formatting[/bold green]")
            console.print("[bold cyan][IntentScout] Fast-Path Activated: CHURN[/bold cyan]")

            # Lock the intent dynamically and skip Vector DB!
            blackboard.taxonomy_id = "GENERIC_CHURN"
            blackboard.intent_nature = "CHURN"
            blackboard.safety_level = "TOTAL"
            blackboard.execution_constraint = "Preserve all existing logic exactly. Apply only formatting, comments, or docstring changes without modifying the AST."
            return  # Exits the IntentScout immediately, moving to RagAgent

        try:
            # Initialize persistent local Chroma client
            client = chromadb.PersistentClient(path=self.chroma_db_path)
            collection = client.get_or_create_collection(
                name="refactoring_taxonomy",
                embedding_function=self.ef
            )

            if not self._ingest_taxonomy(collection):
                console.print(
                    "[bold yellow][IntentScout] Failed to load taxonomy. Falling back to generic safety constraints.[/bold yellow]")
                return

            # Perform Vector Search against the user's prompt
            results = collection.query(
                query_texts=[blackboard.task_description],
                n_results=4,  # Fetch top 4 to power the Consultant Pattern fallback
                include=["metadatas", "distances"]
            )

            if not results['ids'] or not results['ids'][0]:
                console.print("[bold yellow][IntentScout] No deterministic match found.[/bold yellow]")
                return

            # Extract the top match data (Primary Guess)
            match_id = results['ids'][0][0]
            match_meta = results['metadatas'][0][0]
            distance = results['distances'][0][0]

            # Unconditional Human-In-The-Loop Verification
            console.print(
                f"\n[bold cyan][IntentScout] Proposal[/bold cyan] [dim](Vector Distance: {distance:.2f})[/dim]")
            console.print(
                f"The AI mapped your prompt to: [bold]'{match_meta['name']}'[/bold] (Nature: {match_meta['nature']})")

            while True:
                choice = input(f"Are you attempting a '{match_meta['name']}' refactoring? [y/N]: ").strip().lower()
                if choice == 'y':
                    console.print("[bold green]Intent locked by developer.[/bold green]")
                    # Inject the constraints into the Blackboard
                    blackboard.taxonomy_id = match_id
                    blackboard.intent_nature = match_meta["nature"]
                    blackboard.safety_level = match_meta["safety_level"]
                    blackboard.execution_constraint = match_meta["execution_constraint"]

                    # Display the routing decision
                    console.print(
                        f"  [dim]• Executing:[/dim] [bold]{match_meta['name']}[/bold] | [dim]Safety Tier:[/dim] [bold]{match_meta['safety_level']}[/bold]")
                    break
                elif choice in ('n', ''):
                    # --- The Consultant Hard Stop ---
                    console.print("\n[bold red]Intent locked by developer: REJECTED.[/bold red]")
                    console.print("[yellow]Execution Aborted: The AI mapped your intent incorrectly.[/yellow]")
                    console.print("\n[bold]To proceed safely, please review the closest architectural rules for your prompt and try again:[/bold]")

                    # Display alternative options (skipping index 0 since it was rejected)
                    for idx, meta in enumerate(results['metadatas'][0][1:4]):
                        console.print(f"  {idx + 1}. [bold cyan]{meta['name']}[/bold cyan] (Nature: {meta['nature']})")

                    import sys
                    sys.exit(0)
                else:
                    console.print("Invalid input. Please enter 'y' or 'n'.")

        except Exception as e:
            console.print(f"[bold red][IntentScout] Vector Search Failed: {e}[/bold red]")