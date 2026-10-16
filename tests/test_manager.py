"""Regression tests using the real manager and HA entry task lifecycle."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest


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
