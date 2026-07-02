# agents/den_agent.py
import os
from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.dom_scanner import RepoDOMScanner

class MemoryDenAgent(BaseAgent):
    """
    Tier 3: The Repository Awareness Agent.
    Uses the DOM Scanner to map imports, build the local dependency graph,
    and inject structural signatures into the Blackboard.
    """
    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir

    def execute(self, blackboard: ContextBlackboard) -> None:
        # 1. The Semantic Short-Circuit
        if getattr(blackboard, 'intent_nature', None) == "CHURN":
            print("[DenAgent] Task is CHURN. Bypassing dependency extraction to save context tokens.")
            return

        # Booting the Tier 3 Memory Den
        print("[DenAgent] Scanning repository DOM and mapping dependencies...")

        if not os.path.exists(blackboard.target_file):
            print(f"[DenAgent] Target file '{blackboard.target_file}' not found. Skipping DOM injection.")
            return

        # 1. Boot the Engine and map the repository
        scanner = RepoDOMScanner(root_dir=self.root_dir)
        scanner.build_dom()

        # 2. Resolve downstream dependencies (The Graph)
        dependencies = scanner.resolve_downstream_dependencies(blackboard.target_file)

        if not dependencies:
            print("[DenAgent] No local downstream dependencies found via imports.")
            return

        print(f"[DenAgent] Found {len(dependencies)} local dependencies. Extracting signatures...")

        # 3. Extract Signatures and Inject into Blackboard
        den_block = "The following files represent the local dependency graph for your target file. Use these signatures to ensure your code compiles against existing interfaces:\n\n"

        for dep_path in dependencies:
            signature = scanner.structural_grep(dep_path)
            if signature:
                den_block += f"--- {dep_path} ---\n{signature}\n\n"

        blackboard.den_context.append(den_block.strip())
        print("[DenAgent] Memory Den context injected successfully.")