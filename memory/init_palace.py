import sqlite3
import os
import yaml


def build_native_palace():
    print("Initializing Native SQLite Memory Palace...")

    db_path = "./memory/palace.db"
    yaml_path = "./palace.yaml"  # Looks for the user's custom rules file

    # 1. Setup Database Connection
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2. Create the Tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_constraints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_keyword TEXT UNIQUE NOT NULL,
            constraint_text TEXT NOT NULL,
            severity TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_file TEXT NOT NULL,
            previous_prompt TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Dynamically Ingest User's Custom Rules (If provided)
    if os.path.exists(yaml_path):
        print(f"Found custom configuration at {yaml_path}. Ingesting team rules...")
        try:
            with open(yaml_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)

            if config and 'rules' in config:
                team_rules = [
                    (rule['trigger'], rule['constraint'], rule['severity'])
                    for rule in config['rules']
                ]

                cursor.executemany('''
                    INSERT OR IGNORE INTO team_constraints (trigger_keyword, constraint_text, severity)
                    VALUES (?, ?, ?)
                ''', team_rules)
                print(f"Successfully ingested {len(team_rules)} custom rules.")
        except Exception as e:
            print(f"Error parsing {yaml_path}: {e}")
    else:
        print("No custom palace.yaml found. Proceeding with a blank slate.")

    conn.commit()
    conn.close()
    print(f"Memory Palace locked and loaded at {db_path}")


if __name__ == "__main__":
    build_native_palace()