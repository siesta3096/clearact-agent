from clearact.domain.models import ChatMessage


def compact_messages(messages: list[ChatMessage], keep_recent: int = 6) -> list[ChatMessage]:
    if len(messages) <= keep_recent:
        return messages
    old = messages[:-keep_recent]
    recent = messages[-keep_recent:]
    summary = "\n".join(f"{message.role}: {(message.content or '')[:240]}" for message in old)
    return [ChatMessage(role="system", content=f"Earlier task summary:\n{summary}")] + recent
