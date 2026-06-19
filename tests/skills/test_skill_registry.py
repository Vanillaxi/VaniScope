from webscoper.skills.registry import create_default_skill_registry


def test_default_registry_registers_docs_research() -> None:
    registry = create_default_skill_registry()

    skill = registry.get("docs_research")

    assert skill.definition.skill_id == "docs_research"
    assert "docs_research" in skill.definition.supported_task_types
    assert "browser_extract" in skill.definition.required_tools
