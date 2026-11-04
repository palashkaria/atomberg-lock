"""Response-only OTP actions; credentials are never stored in entity state."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN


def register_services(hass):
    async def get_remote_otps(call):
        coordinator = hass.data[DOMAIN].get(call.data["config_entry_id"])
        if coordinator is None:
            raise HomeAssistantError("The selected Atomberg lock is not loaded")
        return {"otps": await coordinator.async_get_remote_otps()}

    async_register_admin_service(
        hass, DOMAIN, "get_remote_otps", get_remote_otps,
        schema=vol.Schema({vol.Required("config_entry_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )
