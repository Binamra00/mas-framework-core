# agents/base_agent.py
from abc import ABC, abstractmethod
from core.blackboard import ContextBlackboard


class BaseAgent(ABC):
    """
    The abstract Strategy interface for all swarm agents.
    Enforces a unified execution method across RAG, Palace, Den, and Coding agents.
    """

    @abstractmethod
    def execute(self, blackboard: ContextBlackboard) -> None:
        """
        Executes the agent's specific behavior and mutates the blackboard state.

        Args:
            blackboard (ContextBlackboard): The central state manager.
        """
        pass