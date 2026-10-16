"""Regression tests using the real manager and HA entry task lifecycle."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.apple_tv import AUTH_EXCEPTIONS


@pytest.mark.parametrize("stage", ["_scan", "_connect"])
async def test_disconnect_awaits_pending_attempt(manager, monkeypatch, stage):
    entered = asyncio.Event()
    finished = asyncio.Event()

    async def pending(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    monkeypatch.setattr(manager, "_scan", AsyncMock(return_value=Mock()))
    monkeypatch.setattr(manager, stage, pending)
    await manager.connect()
    task = manager._task
    await entered.wait()
    await manager.disconnect()
    assert finished.is_set()
    assert task.done()
    assert task.cancelled()
    assert manager._task is None

    monkeypatch.setattr(manager, "_scan", AsyncMock(return_value=None))
    await manager.connect()
    assert manager._task is not task
    await manager.config_entry._async_process_on_unload(manager.hass)
    assert manager._task is None
    assert not manager.config_entry._background_tasks


async def test_old_loop_does_not_clear_replacement_owner(manager, monkeypatch):
    replacement = Mock()

    async def replace(*args, **kwargs):
        manager._task = replacement
        manager.is_on = False

    monkeypatch.setattr(manager, "connect_once", replace)
    task = asyncio.create_task(manager._connect_loop())
    await asyncio.wait_for(task, 0.1)
    assert manager._task is replacement
    manager._task = None


async def test_eager_completed_loop_has_no_owner(manager, monkeypatch):
    async def connected(*args):
        manager.atv = Mock()

    monkeypatch.setattr(manager, "_scan", connected)
    await manager.connect()
    assert manager._task is None


async def test_explicit_connect_interrupts_failed_attempt_backoff(manager, monkeypatch):
    scans = 0
    connected = Mock()

    async def scan():
        nonlocal scans
        scans += 1
        if scans == 2:
            manager.atv = connected

    monkeypatch.setattr(manager, "_scan", scan)
    await manager.connect()
    task = manager._task
    assert manager._connection_attempts == 1
    manager._connection_attempts = 8
    await manager.connect()
    assert manager._connection_attempts == 0
    await asyncio.wait_for(asyncio.shield(task), 0.1)
    assert scans == 2
    assert manager.atv is connected


async def test_reconnect_requested_during_attempt_skips_sleep(manager, monkeypatch):
    scans = 0

    async def scan():
        nonlocal scans
        scans += 1
        if scans == 1:
            await manager.connect()
        else:
            manager.atv = Mock()

    monkeypatch.setattr(manager, "_scan", scan)
    await manager.connect()
    await manager.hass.async_block_till_done()
    assert scans == 2
    assert manager._task is None


@pytest.mark.parametrize("error", AUTH_EXCEPTIONS)
async def test_auth_failure_starts_reauth_and_ends_loop(manager, monkeypatch, error):
    reauth = Mock()
    monkeypatch.setattr(manager.config_entry, "async_start_reauth", reauth)
    monkeypatch.setattr(
        manager, "_scan", AsyncMock(side_effect=error("bad credentials"))
    )
    await manager.connect()
    await manager.hass.async_block_till_done()
    reauth.assert_called_once_with(manager.hass)
    assert manager._task is None
    assert not manager.is_on
    assert not manager.config_entry._background_tasks
