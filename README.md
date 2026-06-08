```
mas-framework-core/
├── agents/                  # The Strategy Pattern implementations
│   ├── base_agent.py
│   ├── rag_agent.py
│   ├── palace_agent.py
│   └── coding_agent.py
├── core/                    # The Engine
│   ├── blackboard.py        # Central state manager
│   └── orchestrator.py      # The main execution loop
├── memory/                  # The Databases
│   ├── den_ingestion.py     # Markdown scraper/parser
│   └── vector_store/        # Local ChromaDB or Faiss instances
├── tests/                   # Automated validation
│   └── test_blackboard.py
├── .gitignore
├── requirements.txt         # transformers, torch, chromadb, etc.
└── README.md
```

# MAS Framework Core (mas-framework-core)

## 1. Architectural Topography

The framework operates as a desktop-native orchestration engine. It separates heavy compute (Inference via external cloud API) from deterministic context retrieval (Local Filesystem). 

### The Central State Engine (Blackboard Pattern)
A centralized `ContextBlackboard` object holds the current task, collects code-quality signals from retrieval steps, and compiles the final optimized context window. Agents never communicate peer-to-peer; they write exclusively to the board.

### The Agent Swarm (Strategy Pattern)
Individual, specialized agents implement a unified execution interface. This allows us to scale the swarm by adding new operational behaviors without altering the core pipeline.

---

## 2. Cognitive Layer Specifications

### Tier 1: The RAG Layer (Universal Truth)
* **Source:** External development standards (e.g., Design patterns, language specifications).
* **Storage:** Localized, lightweight JSON-based vector store or key-value index matching high-level programming paradigms to exact execution principles.

### Tier 2: The Memory Palace (Team Truth)
* **Source:** Local historical graph of past corrections, style definitions, and code-review mandates.
* **Execution:** Prevents repeating structural mistakes by enforcing non-negotiable project boundaries (e.g., immutability constraints or dependency injection preferences).

### Tier 3: The Memory Den (Ground Truth with Alias Grep Router)
Instead of expensive semantic parsing of raw source blocks, the Den constructs a localized structural map (Repo DOM) using documentation, API specifications, and Git Markdown records.

* **The Grep Router:** Tokenizes the path of the target file being edited to isolate precise structural keywords.
* **The Alias Dictionary:** A localized `aliases.json` registry map that bridges the gap between conversational prose and exact file names. 

```
json
{
  "StripeAdapter.java": [
    "external payment gateway",
    "billing processor",
    "stripe credentials"
  ],
  "IPaymentGateway.java": [
    "payment contract",
    "core billing interface"
  ]
}
```
* **Routing Logic:** When the Den Agent triggers a scan for `StripeAdapter.java`, the router extracts both the literal filename tokens and any string values mapped inside the Alias Dictionary. It runs a blazing-fast local `grep` / `ripgrep` command across the project documentation for this expanded token array, fetching exact, contextually rich matches without bloating the prompt with raw source code.

---

## 3. The 2-Week Production Roadmap

| Phase | Focus Component | Target Deliverables |
| :--- | :--- | :--- |
| **Day 1–3** | **Core Infrastructure** | Initialize production Git repo; establish the virtual environment schema; implement the base `ContextBlackboard` and abstract `BaseAgent` Strategy classes. |
| **Day 4–6** | **RAG & Palace Agents** | Build the localized key-value retrieval mechanics for universal architectural rules; construct the file-based parser for historical team corrections. |
| **Day 7–10** | **The Den & Alias Router** | Implement the text-based directory tree scanner (Repo DOM); integrate the `grep` search pipeline along with the `aliases.json` translation block. |
| **Day 11–12** | **Inference Integration** | Build the HTTPS payload orchestrator to securely stream the finalized Blackboard context to the DeepSeek API endpoint and capture clean source blocks. |
| **Day 13–14** | **End-to-End Validation** | Wire the component pipeline together; run deterministic execution tests on targeted file blocks; handle automated error trapping. |