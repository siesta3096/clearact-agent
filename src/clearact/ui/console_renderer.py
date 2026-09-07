from rich.console import Console
from rich.text import Text

from clearact.domain.enums import RiskLevel, ViewMode
from clearact.domain.models import RunEvent


class ConsoleRenderer:
    _STYLES = {
        RiskLevel.WHITE: "white",
        RiskLevel.GREEN: "green",
        RiskLevel.YELLOW: "yellow",
        RiskLevel.RED: "red",
    }
    _MARKERS = {
        RiskLevel.WHITE: "⚪",
        RiskLevel.GREEN: "🟢",
        RiskLevel.YELLOW: "🟡",
        RiskLevel.RED: "🔴",
    }

    def __init__(self, view_mode: ViewMode = ViewMode.SIMPLE, console: Console | None = None) -> None:
        self._view_mode = view_mode
        self._console = console or Console()

    async def handle(self, event: RunEvent) -> None:
        prefix = ""
        style = "cyan"
        if event.risk:
            prefix = f"{self._MARKERS[event.risk]} "
            style = self._STYLES[event.risk]
        line = Text(f"{prefix}{event.title}", style=style)
        if event.detail:
            line.append(f" · {event.detail}", style="dim")
        self._console.print(line)
        if self._view_mode == ViewMode.EXPERT and event.data:
            self._console.print(event.data, style="dim")

    def print_final(self, content: str) -> None:
        self._console.print("\n[bold green]结果[/bold green]")
        self._console.print(content)
