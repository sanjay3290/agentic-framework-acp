from acp_agent_framework.state import State

def test_state_set_and_get():
    state = State()
    state.set("name", "Sanjay")
    assert state.get("name") == "Sanjay"

def test_state_get_default():
    state = State()
    assert state.get("missing") is None
    assert state.get("missing", "default") == "default"

def test_state_delta_tracking():
    state = State()
    state.set("key1", "value1")
    state.set("key2", "value2")
    assert state.get_delta() == {"key1": "value1", "key2": "value2"}

def test_state_commit_clears_delta():
    state = State()
    state.set("key1", "value1")
    state.commit()
    assert state.get_delta() == {}
    assert state.get("key1") == "value1"

def test_state_temp_prefix_not_persisted():
    state = State()
    state.set("temp:scratchpad", "data")
    state.set("name", "Sanjay")
    assert state.get("temp:scratchpad") == "data"
    persistable = state.get_persistable()
    assert "temp:scratchpad" not in persistable
    assert "name" in persistable

def test_state_from_dict():
    state = State(initial={"existing": "data"})
    assert state.get("existing") == "data"
    assert state.get_delta() == {}
