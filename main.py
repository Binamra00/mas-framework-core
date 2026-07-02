from core.blackboard import ContextBlackboard
from agents.rag_agent import RagRetrievalAgent
from agents.palace_agent import MemoryPalaceAgent

if __name__ == "__main__":
    print("Booting MAS Swarm...")

    # 1. Initialize the Blackboard
    board = ContextBlackboard(
        target_file="src/core/adapters/StripeAdapter.java",
        task_description="Build a new Stripe adapter using constructor injection."
    )

    # 2. Register the Swarm Agents
    # Notice how we can dynamically add/remove agents without breaking the board.
    pipeline = [
        RagRetrievalAgent(),
        MemoryPalaceAgent()
        # MemoryDenAgent() -> will be added next!
    ]

    # 3. Execute the Swarm
    for agent in pipeline:
        agent.execute(board)

    # 4. Output the Result
    print("\n--- DYNAMIC API PAYLOAD ---")
    print(board.compile_payload())
    if board.errors:
        print("\nERRORS:", board.errors)