from issuepilot.domain import SearchHit, ToolExecution


def execute_read_only_tools(
    selected_tools: tuple[str, ...], hits: list[SearchHit]
) -> tuple[ToolExecution, ...]:
    executions = []
    for tool in selected_tools:
        if tool == "search_similar_issues":
            issues = [hit.document.title for hit in hits if hit.document.kind == "resolved_issue"]
            summary = (
                f"Resolved issue matches: {', '.join(issues)}"
                if issues
                else "No resolved issue match"
            )
            executions.append(ToolExecution(name=tool, summary=summary))
        elif tool == "get_repository_context":
            kinds = sorted({hit.document.kind for hit in hits})
            executions.append(
                ToolExecution(name=tool, summary=f"Evidence kinds: {', '.join(kinds)}")
            )
        else:
            raise ValueError(f"tool is not allowlisted: {tool}")
    return tuple(executions)
