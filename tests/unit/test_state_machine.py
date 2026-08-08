import pytest

from manny.state import InvalidTransitionError, PrivacyState, RuntimeState, StateMachine


@pytest.mark.asyncio
async def test_valid_interaction_flow_updates_sequence() -> None:
    machine = StateMachine()
    await machine.transition(RuntimeState.IDLE)
    await machine.transition(RuntimeState.LISTENING)
    await machine.transition(RuntimeState.TRANSCRIBING)
    snapshot = await machine.transition(RuntimeState.THINKING)

    assert snapshot.state is RuntimeState.THINKING
    assert snapshot.sequence == 4


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected() -> None:
    machine = StateMachine()

    with pytest.raises(InvalidTransitionError):
        await machine.transition(RuntimeState.SPEAKING)


@pytest.mark.asyncio
async def test_multiple_people_sets_private_context() -> None:
    machine = StateMachine()
    await machine.transition(RuntimeState.IDLE)

    snapshot = await machine.set_presence(2)

    assert snapshot.state is RuntimeState.PRESENT
    assert snapshot.presence is True
    assert snapshot.people_count == 2
    assert snapshot.privacy is PrivacyState.MULTIPLE_PEOPLE
