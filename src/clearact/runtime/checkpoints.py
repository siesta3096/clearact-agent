from __future__ import annotations

import hashlib
import json

from clearact.domain.models import Action, Checkpoint


def fingerprint(action: Action, constraint_version: int = 1) -> str:
    payload = {"tool": action.tool_name, "arguments": action.arguments, "constraint_version": constraint_version}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_checkpoint(run_id: str, action: Action, constraint_version: int = 1) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        action_id=action.id,
        constraint_version=constraint_version,
        input_fingerprint=fingerprint(action, constraint_version),
    )
