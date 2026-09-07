from clearact.domain.models import Action
from clearact.runtime.checkpoints import create_checkpoint, fingerprint
from clearact.storage.checkpoint_store import CheckpointStore


def test_checkpoint_fingerprint_is_stable_for_equivalent_actions():
    first = Action(id="act_one", tool_name="write_file", arguments={"path": "note.txt", "content": "hello"})
    second = Action(id="act_two", tool_name="write_file", arguments={"content": "hello", "path": "note.txt"})

    assert fingerprint(first) == fingerprint(second)


def test_checkpoint_store_persists_completed_action(tmp_path):
    action = Action(id="act_one", tool_name="write_file", arguments={"path": "note.txt", "content": "hello"})
    checkpoint = create_checkpoint("run_one", action)
    store = CheckpointStore(tmp_path / "data")

    store.save(checkpoint)

    path = tmp_path / "data" / "checkpoints" / "run_one.jsonl"
    assert checkpoint.id in path.read_text(encoding="utf-8")
