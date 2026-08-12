from issuepilot.license_audit import audit_required_licenses


def test_reused_agent_dependencies_have_allowed_licenses() -> None:
    assert audit_required_licenses() == {
        "langgraph": "MIT",
        "langgraph-checkpoint-sqlite": "MIT",
        "rank-bm25": "Apache2.0",
    }
