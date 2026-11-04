"""Native options UI for ephemeral OTP results."""
from __future__ import annotations

import voluptuous as vol


class OTPOptionsMixin:
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init", menu_options=["otp_read", "otp_refill", "connection"]
        )

    def _otp_coordinator(self):
        return self.hass.data.get("atomberg_lock", {}).get(self.config_entry.entry_id)

    def _otp_result(self, codes, operation):
        # Never publish codes as entity state, options data, or log messages.
        rows = [f"| {item['slot']} | `{item['code']}` |" for item in codes]
        result = "| Slot | Code |\n| --- | --- |\n" + "\n".join(rows) if rows else "No OTP codes were returned."
        return self.async_show_form(
            step_id="otp_result", data_schema=vol.Schema({}),
            description_placeholders={"operation": operation, "count": str(len(codes)), "codes": result},
        )

    async def async_step_otp_read(self, user_input=None):
        if user_input is not None:
            return await self.async_step_init()
        coordinator = self._otp_coordinator()
        error = "lock_not_loaded" if coordinator is None else None
        if coordinator is not None:
            try:
                codes = await coordinator.async_get_remote_otps()
                return self._otp_result(codes, "OTP pool read completed")
            except Exception:
                error = "otp_read_failed"
        # Submitting this form returns to the menu, rather than retrying silently.
        return self.async_show_form(step_id="otp_read", data_schema=vol.Schema({}), errors={"base": error})

    async def async_step_otp_refill(self, user_input=None):
        errors = {}
        if user_input is not None:
            count = user_input.get("count")
            if type(count) is not int or not 1 <= count <= 10:
                errors["base"] = "invalid_otp_count"
            else:
                coordinator = self._otp_coordinator()
                if coordinator is None:
                    errors["base"] = "lock_not_loaded"
                else:
                    try:
                        codes = await coordinator.async_refill_otps(count)
                        return self._otp_result(codes, "OTP refill acknowledged and verified")
                    except Exception:
                        # A repeat Submit could duplicate a partially successful write.
                        # Require returning to the menu and explicitly starting again.
                        return self.async_show_form(
                            step_id="otp_refill_failed", data_schema=vol.Schema({}),
                            errors={"base": "otp_refill_failed"},
                        )
        return self.async_show_form(
            step_id="otp_refill",
            data_schema=vol.Schema({vol.Required("count", default=1): vol.All(int, vol.Range(min=1, max=10))}),
            errors=errors,
        )

    async def async_step_otp_refill_failed(self, user_input=None):
        return await self.async_step_init()

    async def async_step_otp_result(self, user_input=None):
        return await self.async_step_init()
