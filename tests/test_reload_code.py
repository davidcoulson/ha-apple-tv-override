"""apple_tv.reload_code: the helper that drops modules, and the action itself."""

import sys
import types

from custom_components.apple_tv import _forget_code, _register_reload_code


async def test_forget_code_drops_only_the_package(hass):
    pkg = "custom_components.apple_tv"
    names = (pkg, f"{pkg}.media_player", "custom_components.apple_tv_other")
    saved = {n: sys.modules.get(n) for n in names}
    for name in names:
        sys.modules[name] = types.ModuleType(name)
    hass.data["components"] = {"apple_tv": 1, "apple_tv.remote": 2, "apple_tv_other": 3}
    hass.data["missing_platforms"] = {"apple_tv.zzz": 1}
    try:
        _forget_code(hass, pkg, "apple_tv")
        assert pkg not in sys.modules and f"{pkg}.media_player" not in sys.modules
        assert "custom_components.apple_tv_other" in sys.modules
        assert hass.data["components"] == {"apple_tv_other": 3}
        assert hass.data["missing_platforms"] == {}
    finally:
        for name, module in saved.items():  # put back the real modules
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


async def test_action_is_registered(hass):
    _register_reload_code(hass)
    assert hass.services.has_service("apple_tv", "reload_code")
