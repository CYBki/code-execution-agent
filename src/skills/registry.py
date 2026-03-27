"""Skill detection — maps uploaded files and user queries to relevant skills."""

from __future__ import annotations


SKILL_TRIGGERS: dict[str, dict] = {
    "xlsx": {
        "extensions": [".xlsx", ".xls", ".xlsm"],
        "keywords": ["excel", "spreadsheet", "workbook"],
        "skill_path": "skills/xlsx/SKILL.md",
        "references": {
            "large_files": {
                "path": "skills/xlsx/references/large_files.md",
                "triggers": {
                    "file_size_mb": 40,
                    "keywords": [
                        "large file",
                        "out of memory",
                        "memory error",
                        "duckdb",
                        "million rows",
                        "too big",
                        "very large",
                    ],
                },
            },
            "multi_file_joins": {
                "path": "skills/xlsx/references/multi_file_joins.md",
                "triggers": {
                    "min_files": 2,
                    "keywords": ["join", "merge", "combine", "match", "lookup"],
                },
            },
        },
    },
    "pdf": {
        "extensions": [".pdf"],
        "keywords": ["pdf", "document"],
        "skill_path": "skills/pdf/SKILL.md",
    },
    "csv": {
        "extensions": [".csv", ".tsv"],
        "keywords": ["large file", "duckdb"],
        "skill_path": "skills/csv/SKILL.md",
    },
    "visualization": {
        "extensions": [],
        "keywords": ["chart", "plot", "graph", "visualize", "dashboard", "histogram"],
        "skill_path": "skills/visualization/SKILL.md",
    },
}


def detect_required_skills(
    uploaded_files: list, user_query: str = ""
) -> list[str]:
    """Detect which skills are needed based on files and query."""
    required_skills: set[str] = set()

    for file in uploaded_files:
        ext = "." + file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        for skill_name, config in SKILL_TRIGGERS.items():
            if ext in config["extensions"]:
                required_skills.add(skill_name)

    if user_query:
        query_lower = user_query.lower()
        for skill_name, config in SKILL_TRIGGERS.items():
            # Only add via keyword if not already matched by file extension
            if skill_name not in required_skills:
                if any(kw in query_lower for kw in config["keywords"]):
                    required_skills.add(skill_name)

    return sorted(required_skills)


def detect_reference_files(
    skill_name: str,
    uploaded_files: list,
    user_query: str = "",
) -> list[str]:
    """Detect which reference files should be loaded for progressive disclosure.

    Enables context efficiency: small Excel file = 500 lines (SKILL.md only),
    large Excel file = 800 lines (SKILL.md + large_files.md).
    """
    config = SKILL_TRIGGERS.get(skill_name, {})
    references = config.get("references", {})
    needed_refs: set[str] = set()

    for _ref_name, ref_config in references.items():
        triggers = ref_config["triggers"]

        # Check file size trigger
        if "file_size_mb" in triggers:
            for f in uploaded_files:
                size_mb = f.size / (1024 * 1024)
                if size_mb >= triggers["file_size_mb"]:
                    needed_refs.add(ref_config["path"])
                    break

        # Check file count trigger
        if "min_files" in triggers:
            matching_files = sum(
                1
                for f in uploaded_files
                if any(f.name.endswith(ext) for ext in config.get("extensions", []))
            )
            if matching_files >= triggers["min_files"]:
                needed_refs.add(ref_config["path"])

        # Check keyword trigger
        if user_query and "keywords" in triggers:
            if any(kw in user_query.lower() for kw in triggers["keywords"]):
                needed_refs.add(ref_config["path"])

    return list(needed_refs)
