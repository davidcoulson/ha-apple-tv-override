"""Offline Home Assistant lifecycle fixtures."""

import socket

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.apple_tv import AppleTVManager


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Reject accidental device access in every test."""

    def reject(*args, **kwargs):
        raise AssertionError("Network access is forbidden in these tests")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket.socket, "sendto", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    yield instance
    await instance.async_stop()


@pytest.fixture
async def manager(hass):
    entry = ConfigEntry(
        domain="apple_tv",
        title="Test",
        data={"name": "Test"},
        options={},
        version=1,
        minor_version=1,
        source="user",
        unique_id="test",
        discovery_keys={},
        subentries_data=None,
    )
    instance = AppleTVManager(hass, entry)
    entry.async_on_unload(instance.disconnect)
    yield instance
    await entry._async_process_on_unload(hass)
