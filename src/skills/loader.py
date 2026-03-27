"""Skill loader — parse SKILL.md files and compose progressive system prompts."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def load_skill(skill_name: str) -> dict | None:
    """Load a SKILL.md file and parse its YAML frontmatter + instructions."""
    skill_path = Path(f"skills/{skill_name}/SKILL.md")
    if not skill_path.exists():
        return None

    content = skill_path.read_text(encoding="utf-8")
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            frontmatter = yaml.safe_load(content[4:end])
            instructions = content[end + 5:]
        else:
            frontmatter, instructions = {}, content
    else:
        frontmatter, instructions = {}, content

    return {
        "name": frontmatter.get("name", skill_name),
        "description": frontmatter.get("description", ""),
        "instructions": instructions,
        "path": str(skill_path),
    }


@lru_cache(maxsize=32)
def load_reference(ref_path: str) -> str | None:
    """Load a reference file for progressive disclosure."""
    path = Path(ref_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def compose_system_prompt(
    base_prompt: str,
    active_skills: list[str],
    uploaded_files: list | None = None,
    user_query: str = "",
) -> str:
    """Build system prompt with dynamically loaded skills + reference files.

    Progressive disclosure: SKILL.md always loaded, references only when triggered.
    """
    from src.skills.registry import detect_reference_files

    prompt_parts = [base_prompt]

    for skill_name in active_skills:
        skill = load_skill(skill_name)
        if not skill:
            logger.warning("Skill '%s' not found, skipping", skill_name)
            continue

        prompt_parts.append(
            f"# {skill['name']} Expertise\n\n{skill['instructions']}"
        )

        # Progressive disclosure: load reference files if triggered
        if uploaded_files or user_query:
            ref_paths = detect_reference_files(
                skill_name, uploaded_files or [], user_query
            )
            for ref_path in ref_paths:
                ref_content = load_reference(ref_path)
                if ref_content:
                    ref_name = Path(ref_path).stem.replace("_", " ").title()
                    prompt_parts.append(
                        f"## {ref_name} (Reference)\n\n{ref_content}"
                    )

    return "\n\n".join(prompt_parts)
