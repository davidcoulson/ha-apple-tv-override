# Apple TV (reconnect back-off)

A patched copy of Home Assistant's built-in `apple_tv` integration, from Home
Assistant **2026.9.4**. Installed as a custom integration, it replaces the
built-in one. It changes one thing.

## The problem

An Apple TV in standby that is still reachable on the network accepts a
connection from Home Assistant, announces about 15 seconds later that it is
going to sleep (`TheDeviceIsGoingToSleep`), and stops answering the keep-alive.
pyatv reports the connection lost, and Home Assistant reconnects at once, which
wakes the Apple TV again. The loop runs about once a minute for as long as the
device sleeps:

```
WARNING [homeassistant.components.apple_tv] Connection lost to Apple TV "Home Theater"
WARNING [homeassistant.components.apple_tv] Connection was re-established to device "Home Theater"
```

Home Assistant only backs off after a connection attempt *fails*. Here every
attempt succeeds, so it never backs off. Seen with pyatv 0.18.0; see
[postlund/pyatv#2893](https://github.com/postlund/pyatv/issues/2893).

## The change

A connection lost within 120 seconds of being made counts as short-lived. Each
short-lived connection in a row doubles the wait before the next attempt:
30 s, 60 s, 120 s, 240 s, then 300 s.

- A connection that lasts longer than 120 seconds resets the wait.
- Turning the Apple TV on from Home Assistant reconnects at once.
- Only the first drop is logged as a warning; the repeats go to debug.

**Trade-off:** if somebody wakes a sleeping Apple TV with its own remote, Home
Assistant can take up to five minutes to notice.

Everything is in `custom_components/apple_tv/__init__.py`;
`reconnect-backoff.patch` is the exact difference from Home Assistant's file.

## After a Home Assistant upgrade

This copy does not follow Home Assistant. After an upgrade, copy the new
`homeassistant/components/apple_tv` over `custom_components/apple_tv`, re-apply
`reconnect-backoff.patch`, and put `"version"` back in `manifest.json`. Remove
the override once Home Assistant or pyatv handles the sleep announcement.

## Tests

```bash
pip install pytest pytest-asyncio homeassistant pyatv==0.18.0
pytest tests
```
