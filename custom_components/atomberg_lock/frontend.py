"""Serve and auto-register the bundled OTP dashboard card."""
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

CARD_VERSION = "1.0.2-beta.3"
CARD_PATH = "/atomberg_lock/atomberg-otp-card.js"


async def async_register_card(hass):
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_PATH, str(Path(__file__).parent / "frontend" / "atomberg-otp-card.js"), False)
    ])
    add_extra_js_url(hass, f"{CARD_PATH}?v={CARD_VERSION}")
