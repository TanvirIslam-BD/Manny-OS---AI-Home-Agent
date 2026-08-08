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


@pytest.mark.asyncio
async def test_presence_does_not_clear_explicit_privacy_lock() -> None:
    machine = StateMachine()
    await machine.transition(
        RuntimeState.IDLE,
        force=True,
        privacy=PrivacyState.PRIVACY_LOCKED,
    )

    snapshot = await machine.set_presence(1)

    assert snapshot.state is RuntimeState.PRESENT
    assert snapshot.presence is True
    assert snapshot.people_count == 1
    assert snapshot.privacy is PrivacyState.PRIVACY_LOCKED


@pytest.mark.asyncio
async def test_presence_is_ignored_when_camera_is_disabled() -> None:
    machine = StateMachine()
    disabled = await machine.transition(
        RuntimeState.CAMERA_DISABLED,
        force=True,
        camera_enabled=False,
        privacy=PrivacyState.PRIVACY_LOCKED,
    )

    snapshot = await machine.set_presence(1)

    assert snapshot == disabled
    assert snapshot.state is RuntimeState.CAMERA_DISABLED
    assert snapshot.presence is False
    assert snapshot.people_count == 0
    assert snapshot.privacy is PrivacyState.PRIVACY_LOCKED
