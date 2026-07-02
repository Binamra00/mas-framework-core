from typing import List, Optional


class ContextBlackboard:
    """
    The central state manager for the MAS Framework.
    Agents read from and append to this board. They never interact directly.
    """

    def __init__(self, target_file: str, task_description: str):
        self.target_file: str = target_file
        self.task_description: str = task_description

        # Cognitive Layers
        self.rag_context: List[str] = []
        self.palace_context: List[str] = []
        self.session_context: List[str] = []  # Progressive Prompting
        self.den_context: List[str] = []

        # Output State
        self.generated_code: Optional[str] = None
        self.errors: List[str] = []

        # Triage Agent State
        self.target_entity_name: str = None
        self.target_entity_code: str = None

        # Intent Scout State (Deterministic Classification)
        self.taxonomy_id: str = None
        self.intent_nature: str = None
        self.safety_level: str = None
        self.execution_constraint: str = None

        # History Manager Undo/Redo State
        self.patch_successful: bool = False
        self.progressive_context: list = []

        # Inspector Agent State
        self.original_file_content: str = None
        self.proposed_new_code: str = None

    def compile_payload(self) -> str:
        prompt = f"Target File: {self.target_file}\n"
        prompt += f"Task: {self.task_description}\n\n"

        if self.rag_context:
            prompt += "[Tier 1: Universal Architectural Rules]\n"
            prompt += "\n".join(self.rag_context) + "\n\n"

        if self.palace_context:
            prompt += "[Tier 2: Team Memory & Constraints]\n"
            prompt += "\n".join(self.palace_context) + "\n\n"

        if self.session_context:
            prompt += "[Tier 2.5: Progressive Session History]\n"
            prompt += "\n".join(self.session_context) + "\n\n"

        if self.den_context:
            prompt += "[Tier 3: Repository Ground Truth]\n"
            prompt += "\n".join(self.den_context) + "\n\n"

        prompt += "Constraint: Output only raw, production-ready code. Do not output markdown blocks or conversational text."

        return prompt