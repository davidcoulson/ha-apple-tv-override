"""The override's one change: back off after short-lived connections."""

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest

from custom_components import apple_tv
from custom_components.apple_tv import AppleTVManager, reconnect_delay


def test_delay_doubles_up_to_the_limit():
    assert [reconnect_delay(n) for n in range(7)] == [0, 30, 60, 120, 240, 300, 300]


class _Manager(AppleTVManager):
    """The real manager with the network replaced by a counter."""

    def __init__(self):
        entry = SimpleNamespace(options={}, data={"name": "Test"}, title="Test")
        entry.async_create_background_task = (
            lambda hass, coro, name, eager_start=True: asyncio.ensure_future(coro)
        )
        super().__init__(SimpleNamespace(), entry)
        self.attempts = []

    def _dispatch_send(self, *_args):
        pass

    async def connect_once(self, raise_missing_credentials):
        self.attempts.append(time.monotonic())
        self.atv = SimpleNamespace(close=lambda: None)
        self._connected_at = time.monotonic()
        self._connection_was_lost = False


@pytest.fixture
def fast(monkeypatch):
    # 30 s, 60 s ... become 0.03 s, 0.06 s ... capped at 0.3 s
    monkeypatch.setattr(apple_tv, "BACKOFF_TIME_LOWER_LIMIT", 0.015)
    monkeypatch.setattr(apple_tv, "BACKOFF_TIME_UPPER_LIMIT", 0.3)


async def _settled(m, attempts):
    """Wait until the manager has made this many attempts and its loop has ended."""
    for _ in range(400):
        if len(m.attempts) >= attempts and m._task is None:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"expected {attempts} attempts, saw {len(m.attempts)}")


async def _connected():
    """A manager whose first connection is up."""
    m = _Manager()
    await m.connect()
    await _settled(m, 1)
    return m


async def _drop_and_reconnect(m, skip_wait=True):
    n = len(m.attempts)
    m.connection_lost(Exception())
    if skip_wait:
        m._reconnect_now.set()
    await _settled(m, n + 1)


async def test_short_lived_connections_wait_longer_each_time(fast):
    m = await _connected()

    m.connection_lost(Exception())  # lost at once: short-lived
    await _settled(m, 2)
    first_wait = m.attempts[1] - m.attempts[0]
    m.connection_lost(Exception())
    await _settled(m, 3)
    second_wait = m.attempts[2] - m.attempts[1]

    assert 0.03 <= first_wait < 0.06
    assert 0.06 <= second_wait < 0.12


async def test_a_connection_that_lasted_resets_the_backoff(fast, monkeypatch):
    m = await _connected()
    await _drop_and_reconnect(m)
    assert m._short_lived_connections == 1

    # Every connection now counts as long-lived.
    monkeypatch.setattr(apple_tv, "SHORT_LIVED_CONNECTION", 0)
    started = time.monotonic()
    await _drop_and_reconnect(m, skip_wait=False)
    assert m._short_lived_connections == 0
    assert time.monotonic() - started < 0.02  # reconnected at once, no back-off


async def test_turning_it_on_skips_the_wait(fast):
    m = await _connected()
    for _ in range(4):
        await _drop_and_reconnect(m)
    m.connection_lost(Exception())  # now facing the longest wait (0.3 s here)
    await asyncio.sleep(0.02)
    n = len(m.attempts)
    assert m._task is not None  # still waiting
    await m.connect()  # somebody asks for the device
    await _settled(m, n + 1)
    assert m.attempts[-1] - m.attempts[-2] < 0.1


async def test_only_the_first_drop_is_a_warning(fast, caplog):
    m = await _connected()
    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            await _drop_and_reconnect(m)
    lost = [r.levelname for r in caplog.records if "Connection lost" in r.getMessage()]
    assert lost == ["WARNING", "DEBUG", "DEBUG"]
