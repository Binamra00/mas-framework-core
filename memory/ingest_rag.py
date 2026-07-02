import os
import yaml
import chromadb


def build_decoupled_rag():
    data_dir = "./memory/rag_data"
    print(f"Scanning {data_dir} for categorized pattern definitions...")

    # 1. Setup persistent local storage
    client = chromadb.PersistentClient(path="./memory/chroma_db")

    # Reset collection for a clean slate during ingestion
    try:
        client.delete_collection(name="refactoring_guru_patterns")
    except Exception:
        pass

    collection = client.create_collection(name="refactoring_guru_patterns")

    ids = []
    metadatas = []
    documents = []

    # 2. Iterate through all YAML files in the directory
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created {data_dir}. Please add your .yaml files here.")
        return

    for filename in os.listdir(data_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(data_dir, filename)

            with open(filepath, 'r', encoding='utf-8') as file:
                try:
                    yaml_file = yaml.safe_load(file)

                    # Extract the top-level category context
                    category_name = yaml_file.get("category", "Unknown")
                    category_def = yaml_file.get("def", "")
                    patterns_list = yaml_file.get("patterns", [])

                    for pattern_data in patterns_list:
                        # Validate required schema fields
                        if not all(k in pattern_data for k in ["id", "name", "intent"]):
                            print(f"Skipping a pattern in {filename}: Missing required keys.")
                            continue

                        ids.append(pattern_data["id"])

                        # Store structured metadata for precise filtering later
                        metadatas.append({
                            "category": category_name,
                            "name": pattern_data["name"]
                        })

                        # Inject the category definition into the specific pattern's chunk.
                        # This ensures the agent always understands the overarching behavioral/structural context
                        # without needing to fetch the entire parent document.
                        chunk_data = {
                            "category": category_name,
                            "category_definition": category_def,
                            **pattern_data
                        }

                        # Dump the enriched pattern structure into the vector document
                        documents.append(yaml.dump(chunk_data, sort_keys=False))

                        print(f"Processed: {pattern_data['name']} ({category_name})")

                except yaml.YAMLError as exc:
                    print(f"Error parsing {filename}: {exc}")

    # 3. Ingest into ChromaDB
    if ids:
        print(f"\nIngesting {len(ids)} decoupled patterns into vector space...")
        collection.add(
            ids=ids,
            metadatas=metadatas,
            documents=documents
        )
        print("RAG Ingestion Complete. Database saved to ./memory/chroma_db/")
    else:
        print("No valid YAML patterns found to ingest.")


if __name__ == "__main__":
    build_decoupled_rag()