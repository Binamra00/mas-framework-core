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