"""Pairing resource cleanup, including the Home Assistant flow removal lifecycle."""

from collections import deque
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntries
from pyatv import exceptions
from pyatv.const import PairingRequirement, Protocol

from custom_components.apple_tv import config_flow
from custom_components.apple_tv.config_flow import AppleTVConfigFlow


@pytest.fixture
async def flow(hass, monkeypatch):
    hass.config_entries = ConfigEntries(hass, {})
    instance = AppleTVConfigFlow()
    instance.init_step = "user"
    monkeypatch.setattr(
        hass.config_entries.flow, "async_create_flow", AsyncMock(return_value=instance)
    )
    await hass.config_entries.flow.async_init("apple_tv", context={"source": "user"})
    yield instance
    if hass.config_entries.flow.async_progress():
        hass.config_entries.flow.async_abort(instance.flow_id)
    await hass.async_block_till_done()


async def test_abort_closes_pairing_once(flow, hass):
    pairing = Mock(close=AsyncMock())
    flow.pairing = pairing
    hass.config_entries.flow.async_abort(flow.flow_id)
    assert flow.pairing is None
    flow.async_remove()
    await hass.async_block_till_done()
    pairing.close.assert_awaited_once()


@pytest.mark.parametrize(
    "error,reason",
    [
        (exceptions.PairingError, "invalid_auth"),
        (RuntimeError, "unknown"),
        (None, "device_did_not_pair"),
    ],
)
async def test_no_pin_failure_cleans_up(flow, hass, error, reason):
    pairing = Mock(
        close=AsyncMock(),
        finish=AsyncMock(side_effect=error() if error else None),
        has_paired=False,
    )
    flow.protocol = Protocol.AirPlay
    flow.pairing = pairing
    flow.cur_step = flow.async_show_form(step_id="pair_no_pin")
    result = await hass.config_entries.flow.async_configure(flow.flow_id, {})
    assert result["reason"] == reason
    assert flow.pairing is None
    flow.async_remove()
    pairing.close.assert_awaited_once()


@pytest.mark.parametrize("stage", ["create", "begin"])
@pytest.mark.parametrize(
    "error,reason",
    [
        (exceptions.ConnectionFailedError, None),
        (exceptions.BackOffError, "backoff"),
        (exceptions.PairingError, "invalid_auth"),
        (RuntimeError, "unknown"),
    ],
)
async def test_pairing_creation_and_begin_errors(
    flow, monkeypatch, stage, error, reason
):
    flow.atv = Mock()
    flow.atv.get_service.return_value = Mock(
        requires_password=False, pairing=PairingRequirement.Mandatory
    )
    flow.protocols_to_pair = deque([Protocol.AirPlay])
    pairing = Mock(
        close=AsyncMock(),
        begin=AsyncMock(side_effect=error() if stage == "begin" else None),
    )
    monkeypatch.setattr(config_flow, "async_get_clientsession", Mock())
    monkeypatch.setattr(
        config_flow,
        "pair",
        AsyncMock(
            return_value=pairing, side_effect=error() if stage == "create" else None
        ),
    )
    result = await flow.async_pair_next_protocol()
    if reason:
        assert result["reason"] == reason
    else:
        assert result["step_id"] == "service_problem"
    assert flow.pairing is None
    if stage == "begin":
        pairing.close.assert_awaited_once()


async def test_cleanup_detaches_even_if_close_fails(flow):
    pairing = Mock(close=AsyncMock(side_effect=RuntimeError))
    flow.pairing = pairing
    with pytest.raises(RuntimeError):
        await flow._async_cleanup()
    await flow._async_cleanup()
    assert flow.pairing is None
    pairing.close.assert_awaited_once()
