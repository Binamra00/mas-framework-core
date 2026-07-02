# agents/palace_agent.py
import sqlite3
import os
from core.blackboard import ContextBlackboard
from agents.base_agent import BaseAgent
from core.history_manager import HistoryManager
from rich.console import Console

console = Console()


class MemoryPalaceAgent(BaseAgent):
    """
    Tier 2: Queries native SQLite for team constraints AND
    historical session context for progressive prompting via HistoryManager.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.history_mgr = HistoryManager(db_path)

    def execute(self, blackboard: ContextBlackboard) -> None:
        if not os.path.exists(self.db_path):
            console.print(
                f"[bold yellow][PalaceAgent] Database not found at {self.db_path}. Skipping rules.[/bold yellow]")
            return

        # --- 1. Evaluate Static Team Rules (Original Logic Preserved) ---
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                search_context = f"{blackboard.target_file} {blackboard.task_description}".lower()
                cursor.execute("SELECT trigger_keyword, constraint_text, severity FROM team_constraints")
                all_rules = cursor.fetchall()

                for keyword, constraint_text, severity in all_rules:
                    if keyword.lower() in search_context:
                        formatted_rule = f"[{severity} TEAM RULE] {constraint_text}"
                        # Ensure the blackboard list exists before appending
                        if not hasattr(blackboard, 'palace_context'):
                            blackboard.palace_context = []
                        blackboard.palace_context.append(formatted_rule)
                        console.print(f"[bold red][PalaceAgent][/bold red] Triggered constraint for: '{keyword}'")
        except sqlite3.OperationalError:
            pass  # Failsafe if team_constraints table doesn't exist yet

        # --- 2. Evaluate Progressive Prompting History (Upgraded to Time Machine) ---
        context = self.history_mgr.get_progressive_context(blackboard.target_file)

        if context:
            blackboard.progressive_context = context
            console.print(
                f"[bold blue][PalaceAgent][/bold blue] Loaded progressive context ({len(context)} recent actions).")
        else:
            console.print("[bold blue][PalaceAgent][/bold blue] No prior timeline history found.")