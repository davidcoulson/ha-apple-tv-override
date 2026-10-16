"""Offline media player regressions with the real connection manager."""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.media_player import MediaType
from homeassistant.exceptions import HomeAssistantError

from custom_components.apple_tv import media_player
from custom_components.apple_tv.media_player import AppleTvMediaPlayer, _redact_media_id


async def test_turn_on_reconnects_then_sends_power(manager, monkeypatch):
    player = AppleTvMediaPlayer("Test", "test", manager)
    atv = Mock()
    atv.power.turn_on = AsyncMock()

    async def connect(*args):
        await asyncio.sleep(0)
        manager.atv = atv

    monkeypatch.setattr(manager, "_scan", AsyncMock(return_value=Mock()))
    monkeypatch.setattr(manager, "_connect", connect)
    manager.is_on = False
    await player.async_turn_on()
    assert manager.is_on
    atv.power.turn_on.assert_awaited_once()


async def test_turn_on_times_out_without_cancelling_manager(manager, monkeypatch):
    player = AppleTvMediaPlayer("Test", "test", manager)
    monkeypatch.setattr(manager, "_scan", AsyncMock(return_value=None))
    monkeypatch.setattr(media_player, "TURN_ON_TIMEOUT", 0.01)
    await manager.connect()
    task = manager._task
    with pytest.raises(HomeAssistantError, match="Timed out"):
        await player.async_turn_on()
    assert manager._task is task
    assert not task.done()


async def test_turn_on_reports_failed_connection(manager, monkeypatch):
    player = AppleTvMediaPlayer("Test", "test", manager)

    async def stop():
        manager.is_on = False

    monkeypatch.setattr(manager, "_scan", stop)
    with pytest.raises(HomeAssistantError, match="Failed to connect"):
        await player.async_turn_on()


@pytest.mark.parametrize("stream_file", [True, False])
async def test_playback_logs_redacted_url(manager, monkeypatch, caplog, stream_file):
    player = AppleTvMediaPlayer("Test", "test", manager)
    player.atv = Mock()
    player.atv.stream.stream_file = AsyncMock()
    player.atv.stream.play_url = AsyncMock()
    monkeypatch.setattr(
        player,
        "_is_feature_available",
        lambda feature: (
            stream_file if feature is media_player.FeatureName.StreamFile else True
        ),
    )
    url = (
        "https://alice:secret@example.com/song?token=private&Access_Key=hidden&track=2"
    )
    with caplog.at_level(logging.DEBUG):
        await player.async_play_media(MediaType.MUSIC, url)
    for secret in ("alice", "secret", "private", "hidden"):
        assert secret not in caplog.text
    assert "track=2" in caplog.text
    command = (
        player.atv.stream.stream_file if stream_file else player.atv.stream.play_url
    )
    command.assert_awaited_once_with(url)


@pytest.mark.parametrize(
    "media_id", ["/media/song.mp3", "/media/file?token=local", "relative.mp3"]
)
def test_redaction_preserves_file_paths(media_id):
    assert _redact_media_id(media_id) == media_id


async def test_turn_on_uses_existing_connection(manager, monkeypatch):
    player = AppleTvMediaPlayer("Test", "test", manager)
    player.atv = Mock()
    player.atv.power.turn_on = AsyncMock()
    connect = AsyncMock()
    monkeypatch.setattr(manager, "connect", connect)
    await player.async_turn_on()
    player.atv.power.turn_on.assert_awaited_once()
    connect.assert_not_awaited()


@pytest.mark.parametrize(
    "key",
    [
        "Authorization",
        "access_token",
        "api_key",
        "password",
        "pwd",
        "signature",
        "credentials",
        "sessionid",
        "jwt",
    ],
)
def test_redaction_hides_credential_query_values(key):
    redacted = _redact_media_id(
        f"https://example.com/song?{key}=hidden&{key}=other&track=2"
    )
    assert "hidden" not in redacted
    assert "other" not in redacted
    assert redacted.count("REDACTED") == 2
    assert "track=2" in redacted
