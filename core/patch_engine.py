# core/patch_engine.py
import re


class PatchEngine:
    """Handles the extraction and application of one or more precise code mutations."""

    # Tolerant marker matcher:
    #   - 3+ marker characters (handles the model emitting 6, 7, or 8 of them)
    #   - flexible surrounding spaces/tabs
    #   - re.DOTALL so SEARCH/REPLACE bodies can span multiple lines
    #   - finditer() walks ALL blocks, so multi-method patches work
    _BLOCK_RE = re.compile(
        r'<{3,}[ \t]*SEARCH[ \t]*\n(.*?)\n[ \t]*={3,}[ \t]*\n(.*?)\n[ \t]*>{3,}[ \t]*REPLACE',
        re.DOTALL,
    )

    @staticmethod
    def extract_blocks(raw_response: str) -> list[tuple[str, str]]:
        """Parse ALL SEARCH/REPLACE pairs from an LLM response.

        Returns a list of (search, replace) tuples. Raises if none are found.
        """
        # Strip fence-only lines (```python / ```) without touching real code,
        # so a stray fence around an individual block can't break parsing.
        cleaned = re.sub(r'(?m)^[ \t]*```[a-zA-Z]*[ \t]*$', '', raw_response)

        blocks = [
            (match.group(1), match.group(2))
            for match in PatchEngine._BLOCK_RE.finditer(cleaned)
        ]

        if not blocks:
            raise ValueError(
                "The AI failed to format the response with strict SEARCH/REPLACE markers."
            )

        return blocks

    @staticmethod
    def apply_patch(original_file_content: str, blocks: list[tuple[str, str]]) -> str:
        """Apply each (search, replace) pair in order.

        Every SEARCH block must match exactly once. Application is sequential on the
        progressively mutated content, so small, non-overlapping blocks are safe.
        """
        content = original_file_content

        for index, (search_block, replace_block) in enumerate(blocks, start=1):
            if search_block not in content:
                raise ValueError(
                    f"Safety Abort: SEARCH block #{index} does not exactly match "
                    f"any code in the current file."
                )
            # Replace only the first exact occurrence of this block.
            content = content.replace(search_block, replace_block, 1)

        return content