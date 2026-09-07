from clearact.domain.models import ToolDefinition


class ToolFilter:
    def select(self, tools: list[ToolDefinition], recent_tool_names: set[str]) -> list[ToolDefinition]:
        if not recent_tool_names:
            return tools
        groups = {
            # A search result is discovery, not evidence. After inspecting a
            # source the model may discover a 404, paywall, stale result, or a
            # page unrelated to the requested metric. Keep search available so
            # it can replace invalid evidence; the system prompt bounds this
            # fallback to focused, alternative-source queries.
            "web_search": {"web_search", "fetch_url", "write_file"},
            "fetch_url": {"web_search", "fetch_url", "write_file"},
            "list_files": {"list_files", "read_file", "write_file"},
            "read_file": {"list_files", "read_file", "write_file"},
            "write_file": {"list_files", "read_file", "write_file"},
        }
        allowed = set().union(*(groups.get(name, set()) for name in recent_tool_names))
        return [tool for tool in tools if tool.name in allowed] or tools
