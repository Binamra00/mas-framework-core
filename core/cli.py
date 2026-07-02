# core/cli.py
import os
import sys
import sqlite3
import yaml

# Clean, decoupled imports for the swarm
from core.blackboard import ContextBlackboard
from core.config_manager import ConfigManager
from core.llm_providers import ProviderFactory
from agents.rag_agent import RagRetrievalAgent
from agents.palace_agent import MemoryPalaceAgent
from agents.den_agent import MemoryDenAgent
from agents.coding_agent import UniversalCodingAgent
from agents.triage_agent import TriageAgent
from core.history_manager import HistoryManager
from agents.inspector_agent import InspectorAgent
from agents.intent_scout import IntentScoutAgent
from core import perimeter


def find_project_root(current_dir: str = ".") -> str:
    """
    Traverses upwards to find the project root.
    Strictly requires a recognized ecosystem marker to proceed.
    """
    current = os.path.abspath(current_dir)
    project_markers = [
        "palace.yaml", ".git", "pom.xml", "build.gradle",
        "package.json", "pyproject.toml", "go.mod"
    ]

    while True:
        for marker in project_markers:
            if os.path.exists(os.path.join(current, marker)):
                return current

        parent = os.path.dirname(current)
        if parent == current:
            # We hit the top of the OS drive and found no project markers
            return None
        current = parent


def init_local_db(project_root: str) -> str:
    """Auto-provisions the local SQLite DB at the project root with Auto-Pruning."""
    db_path = os.path.join(project_root, ".mas_palace.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create Constraints Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS team_constraints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_keyword TEXT UNIQUE NOT NULL,
        constraint_text TEXT NOT NULL,
        severity TEXT NOT NULL
    )''')

    # 2. Create Session History Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS file_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_file TEXT NOT NULL,
        previous_prompt TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 3. Create the Auto-Pruning Trigger (The Janitor)
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS prune_old_sessions
        AFTER INSERT ON file_sessions
        BEGIN
            DELETE FROM file_sessions 
            WHERE target_file = NEW.target_file 
            AND id NOT IN (
                SELECT id FROM file_sessions 
                WHERE target_file = NEW.target_file 
                ORDER BY timestamp DESC 
                LIMIT 10
            );
        END;
    ''')

    # 4. Create the DOM Cache Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS dom_cache (
            filepath TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            signatures TEXT NOT NULL,
            last_scanned DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

    # Look for palace.yaml at the project root
    yaml_path = os.path.join(project_root,"config",  "palace.yaml")
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if config and 'rules' in config:
                rules = [(r['trigger'], r['constraint'], r['severity']) for r in config['rules']]
                cursor.executemany('''INSERT OR IGNORE INTO team_constraints 
                                      (trigger_keyword, constraint_text, severity) 
                                      VALUES (?, ?, ?)''', rules)
        except Exception:
            pass

    conn.commit()
    conn.close()
    return db_path


def resolve_target_file(search_term: str, project_root: str) -> str:
    if os.path.exists(search_term):
        return os.path.abspath(search_term)

    print(f"[MAS] Scanning project root '{project_root}' for '{search_term}'...")
    matches = []

    needle = search_term.replace("\\", "/").lower()
    has_sep = "/" in needle

    for root, dirs, files in os.walk(project_root):
        perimeter.prune_dirs(dirs)            # single source of truth
        for file in files:
            if has_sep:
                rel = os.path.join(root, file).replace("\\", "/").lower()
                if rel.endswith("/" + needle) or rel.endswith(needle):
                    matches.append(os.path.join(root, file))
            elif file.lower() == needle:       # exact basename, not substring
                matches.append(os.path.join(root, file))

    if len(matches) == 0:
        print(f"[Error] Could not find any file matching '{search_term}' outside of ignored directories.")
        sys.exit(1)
    if len(matches) == 1:
        print(f"[MAS] Resolved to: {matches[0]}")
        return matches[0]

    print(f"\n[MAS] Found multiple matches for '{search_term}':")
    for i, match in enumerate(matches):
        print(f"  [{i + 1}] {match}")
    while True:
        try:
            choice = int(input("\nSelect the target file (number): "))
            if 1 <= choice <= len(matches):
                return matches[choice - 1]
            print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")


def main():
    if len(sys.argv) < 2:
        print("Usage: mas <command> [args]")
        print("Commands: configure, refactor, undo, redo")
        sys.exit(1)

    command = sys.argv[1]
    project_root = find_project_root()
    if not project_root and command in ["refactor", "undo", "redo"]:
        print("[Error] Must be run from inside a valid project workspace.")
        sys.exit(1)

    db_path = os.path.join(project_root, ".mas_palace.db") if project_root else ""
    history_mgr = HistoryManager(db_path) if project_root else None

    if command == "configure":
        ConfigManager.run_setup_wizard()

    elif command in ["undo", "redo"]:
        if len(sys.argv) < 3:
            print(f"Usage: mas {command} <filename>")
            sys.exit(1)

        target_file = resolve_target_file(sys.argv[2], project_root)

        if command == "undo":
            restored = history_mgr.undo(target_file)
            if restored:
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(restored)
                print(f"[Success] '{target_file}' reverted to previous state.")
            else:
                print(f"[Info] Cannot undo. Oldest state reached for '{target_file}'.")

        elif command == "redo":
            restored = history_mgr.redo(target_file)
            if restored:
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(restored)
                print(f"[Success] '{target_file}' advanced to next state.")
            else:
                print(f"[Info] Cannot redo. Newest state reached for '{target_file}'.")

    elif command == "refactor":
        search_term = sys.argv[2]
        task_prompt = sys.argv[3]
        target_file = resolve_target_file(search_term, project_root)

        # 0. Commit baseline if this file has no history
        if not history_mgr._get_head(target_file):
            with open(target_file, "r", encoding="utf-8") as f:
                history_mgr.commit(target_file, "Initial State", f.read())

        print(f"\n[MAS Orchestrator] Booting swarm for {target_file}...")
        board = ContextBlackboard(target_file=target_file, task_description=task_prompt)
        ai_provider = ProviderFactory.get_provider()

        pipeline = [
            IntentScoutAgent(provider=ai_provider,project_root=project_root),
            RagRetrievalAgent(),
            MemoryPalaceAgent(db_path=db_path),
            MemoryDenAgent(root_dir=project_root),
            TriageAgent(provider=ai_provider),
            UniversalCodingAgent(provider=ai_provider),
            InspectorAgent(provider=ai_provider, project_root=project_root)
        ]

        for agent in pipeline:
            agent.execute(board)

        # 4. Save State on Success
        if board.patch_successful:
            with open(target_file, "r", encoding="utf-8") as f:
                history_mgr.commit(target_file, task_prompt, f.read())
            print("[MAS Orchestrator] Session state committed to timeline.")