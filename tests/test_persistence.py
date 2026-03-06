import pytest
from acp_agent_framework.persistence import JsonSessionStore


def test_save_and_load_session(tmp_path):
    store = JsonSessionStore(tmp_path)
    data = {"state": {"key": "value"}, "history": ["msg1", "msg2"]}
    store.save("sess-1", data)
    loaded = store.load("sess-1")
    assert loaded == data

def test_load_nonexistent_session(tmp_path):
    store = JsonSessionStore(tmp_path)
    assert store.load("nonexistent") is None

def test_list_sessions(tmp_path):
    store = JsonSessionStore(tmp_path)
    store.save("sess-1", {"a": 1})
    store.save("sess-2", {"b": 2})
    sessions = store.list_sessions()
    assert set(sessions) == {"sess-1", "sess-2"}

def test_delete_session(tmp_path):
    store = JsonSessionStore(tmp_path)
    store.save("sess-1", {"a": 1})
    store.delete("sess-1")
    assert store.load("sess-1") is None


@pytest.mark.parametrize("bad_id", [
    "../escape",
    "../../etc/passwd",
    "foo/bar",
    "foo\\bar",
    "..",
    "",
])
def test_path_traversal_rejected(tmp_path, bad_id):
    store = JsonSessionStore(tmp_path)
    with pytest.raises(ValueError, match="Invalid session_id|escapes storage"):
        store.save(bad_id, {"x": 1})
