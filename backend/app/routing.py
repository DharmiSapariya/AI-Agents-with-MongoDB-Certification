"""Pure routing logic (kept free of heavy imports so it is unit-testable)."""
END = "__end__"


def route_tools(state: dict) -> str:
    """Conditional edge: go to 'tools' if the last message requested tool calls, else END."""
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("No messages in state")
    return "tools" if getattr(messages[-1], "tool_calls", None) else END
