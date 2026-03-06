from acp_agent_framework.events import Event, EventActions

def test_event_creation():
    event = Event(author="test-agent", type="message", content="Hello world")
    assert event.author == "test-agent"
    assert event.type == "message"
    assert event.content == "Hello world"
    assert event.id is not None
    assert event.timestamp > 0

def test_event_with_actions():
    actions = EventActions(state_delta={"key": "value"}, transfer_to_agent="other-agent")
    event = Event(author="test-agent", type="message", content="Hello", actions=actions)
    assert event.actions.state_delta == {"key": "value"}
    assert event.actions.transfer_to_agent == "other-agent"

def test_event_actions_defaults():
    actions = EventActions()
    assert actions.state_delta == {}
    assert actions.transfer_to_agent is None
    assert actions.escalate is None
