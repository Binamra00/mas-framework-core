# core/history_manager.py
import os
import sqlite3


class HistoryManager:
    """Manages an SQLite Git-style timeline for file modifications."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS file_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_file TEXT NOT NULL,
                prompt TEXT NOT NULL,
                file_content TEXT NOT NULL,
                taxonomy_rule TEXT,       -- NEW: Stores 'Extract Method (RM_Fowler_1)'
                impacted_entities TEXT,   -- NEW: Stores 'init_local_db, _initialize_database'
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            # --- SEAMLESS MIGRATION FOR EXISTING DATABASES ---
            try:
                conn.execute("ALTER TABLE file_history ADD COLUMN taxonomy_rule TEXT")
                conn.execute("ALTER TABLE file_history ADD COLUMN impacted_entities TEXT")
            except sqlite3.OperationalError:
                pass  # Columns already exist, safe to ignore

            conn.execute('''CREATE TABLE IF NOT EXISTS file_head (
                target_file TEXT PRIMARY KEY,
                current_history_id INTEGER
            )''')

            # --- ADD THIS JANITOR TRIGGER ---
            conn.execute('''
                CREATE TRIGGER IF NOT EXISTS limit_history_bloat
                AFTER INSERT ON file_history
                BEGIN
                    DELETE FROM file_history 
                    WHERE target_file = NEW.target_file 
                    AND id NOT IN (
                        SELECT id FROM file_history 
                        WHERE target_file = NEW.target_file 
                        ORDER BY id DESC 
                        LIMIT 15
                    );
                END;
            ''')

    def _get_head(self, target_file: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT current_history_id FROM file_head WHERE target_file = ?", (target_file,))
            row = cursor.fetchone()
            return row[0] if row else None

    # NEW: Added taxonomy_rule and impacted_entities parameters
    def commit(self, target_file: str, prompt: str, file_content: str, taxonomy_rule: str = None,
               impacted_entities: str = None):
        """Saves a state. Snips alternate timelines if we are detached from HEAD."""
        head_id = self._get_head(target_file)
        with sqlite3.connect(self.db_path) as conn:
            if head_id:
                # If we undid something and now making a new change, delete the alternate future
                conn.execute("DELETE FROM file_history WHERE target_file = ? AND id > ?", (target_file, head_id))

            cursor = conn.execute(
                "INSERT INTO file_history (target_file, prompt, file_content, taxonomy_rule, impacted_entities) VALUES (?, ?, ?, ?, ?)",
                (target_file, prompt, file_content, taxonomy_rule, impacted_entities)
            )
            new_head_id = cursor.lastrowid
            conn.execute("INSERT OR REPLACE INTO file_head (target_file, current_history_id) VALUES (?, ?)",
                         (target_file, new_head_id))

    def undo(self, target_file: str) -> str:
        """Moves HEAD back one step and returns the previous file content."""
        head_id = self._get_head(target_file)
        if not head_id: return None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, file_content FROM file_history WHERE target_file = ? AND id < ? ORDER BY id DESC LIMIT 1",
                (target_file, head_id))
            row = cursor.fetchone()
            if row:
                prev_id, prev_content = row
                conn.execute("UPDATE file_head SET current_history_id = ? WHERE target_file = ?",
                             (prev_id, target_file))
                return prev_content
            return None

    def redo(self, target_file: str) -> str:
        """Moves HEAD forward one step and returns the next file content."""
        head_id = self._get_head(target_file)
        if not head_id: return None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, file_content FROM file_history WHERE target_file = ? AND id > ? ORDER BY id ASC LIMIT 1",
                (target_file, head_id))
            row = cursor.fetchone()
            if row:
                next_id, next_content = row
                conn.execute("UPDATE file_head SET current_history_id = ? WHERE target_file = ?",
                             (next_id, target_file))
                return next_content
            return None

    def get_progressive_context(self, target_file: str, limit: int = 3) -> list:
        """Retrieves the last N actions leading up to the current HEAD formatted as UI breadcrumbs."""
        head_id = self._get_head(target_file)
        if not head_id: return []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT prompt, taxonomy_rule, impacted_entities, timestamp FROM file_history WHERE target_file = ? AND id <= ? ORDER BY id DESC LIMIT ?",
                (target_file, head_id, limit)
            )

            breadcrumbs = []
            for row in cursor.fetchall():
                prompt_text, tax_rule, entities, ts = row
                if prompt_text == "Initial State":
                    continue

                # Format timestamps to look clean (e.g., extracting just the time component or returning the raw SQL format cleanly)
                clean_time = ts.split(".")[0] if ts else "Unknown Time"

                if tax_rule and entities:
                    breadcrumbs.append(f"[{clean_time}] {tax_rule} applied to: {entities}")
                else:
                    breadcrumbs.append(f"[{clean_time}] Manual Refactor: '{prompt_text}'")

            return breadcrumbs[::-1]  # Return in chronological order