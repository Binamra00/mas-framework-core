# core/ast_slicer.py
import ast
import os


class ASTSlicer:
    """
    Programmatically parses a Python file and extracts standalone entities
    (methods, functions) into a dictionary of their raw string implementations,
    along with structural metadata for previews.
    """

    @staticmethod
    def _extract_signature(source_segment: str) -> str:
        """Extracts just the signature line from a source segment."""
        if not source_segment:
            return "Unknown Signature"
        for line in source_segment.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                # Extract up to the end of the signature to keep it clean
                return stripped.rstrip(':')
        return "Signature not found"

    @staticmethod
    def slice_file(filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Cannot slice file. Path not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            source_code = f.read()

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise ValueError(f"Cannot parse {filepath}: Invalid Python syntax. {e}")

        entities = {}
        metadata = {}  # NEW: Store metadata separately to prevent breaking other agents

        def process_node(node, entity_name):
            segment = ast.get_source_segment(source_code, node)
            entities[entity_name] = segment

            # Extract metadata for the Blast Radius preview
            docstring = ast.get_docstring(node)
            size = len(segment.splitlines()) if segment else 0
            signature = ASTSlicer._extract_signature(segment)

            metadata[entity_name] = {
                "signature": signature,
                "docstring": docstring if docstring else "No docstring provided.",
                "size": size
            }

        for node in tree.body:
            # 1. Extract Top-Level Functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                process_node(node, node.name)

            # 2. Extract Class Methods
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Format: ClassName.method_name
                        entity_name = f"{class_name}.{child.name}"
                        process_node(child, entity_name)

        return {
            "filepath": filepath,
            "entities": entities,
            "metadata": metadata  # Pass metadata to the TriageAgent
        }