from collections.abc import Awaitable, Callable

from clearact.domain.models import RunEvent

EventHandler = Callable[[RunEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def subscribe_sync(self, handler: Callable[[RunEvent], None]) -> None:
        async def wrapped(event: RunEvent) -> None:
            handler(event)

        self.subscribe(wrapped)

    async def publish(self, event: RunEvent) -> None:
        for handler in self._handlers:
            await handler(event)
