import json
from pathlib import Path

from clearact.domain.models import Checkpoint


class CheckpointStore:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "checkpoints"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: Checkpoint) -> None:
        path = self._root / f"{checkpoint.run_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(checkpoint.model_dump(mode="json"), ensure_ascii=False) + "\n")
