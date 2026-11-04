"""Native flow behavior tests with a minimal form-host fixture."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location('otp_options', Path(__file__).resolve().parents[1] / 'custom_components/atomberg_lock/otp_options.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Flow(module.OTPOptionsMixin):
    def __init__(self, loaded=True):
        self.coordinator = SimpleNamespace(async_get_remote_otps=AsyncMock(return_value=[{'slot': 12, 'code': '123456'}]), async_refill_otps=AsyncMock(return_value=[{'slot': 13, 'code': '654321'}]))
        self.config_entry = SimpleNamespace(entry_id='lock')
        self.hass = SimpleNamespace(data={'atomberg_lock': {'lock': self.coordinator} if loaded else {}})
    def async_show_form(self, **kwargs):
        return {'type': 'form', **kwargs}
    def async_show_menu(self, **kwargs):
        return {'type': 'menu', **kwargs}

class OptionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_keeps_connection_settings(self):
        self.assertEqual((await Flow().async_step_init())['menu_options'], ['otp_read', 'otp_refill', 'connection'])
    async def test_read_displays_all_slots_and_codes_without_storing_them(self):
        flow=Flow();flow.coordinator.async_get_remote_otps.return_value=[{'slot': 12,'code':'123456'},{'slot':13,'code':'654321'}]
        result=await flow.async_step_otp_read()
        self.assertEqual(result['step_id'],'otp_result')
        self.assertIn('123456',result['description_placeholders']['codes'])
        self.assertIn('654321',result['description_placeholders']['codes'])
        self.assertEqual(dict(result['data_schema'].schema),{})
        self.assertEqual((await flow.async_step_otp_result({}))['type'],'menu')
        self.assertNotIn('123456',str(flow.__dict__))
    async def test_refill_form_does_not_write_until_submitted(self):
        flow=Flow();await flow.async_step_otp_refill()
        flow.coordinator.async_refill_otps.assert_not_awaited()
        result=await flow.async_step_otp_refill({'count':2})
        flow.coordinator.async_refill_otps.assert_awaited_once_with(2)
        self.assertIn('654321',result['description_placeholders']['codes'])
    async def test_partial_failure_requires_return_to_menu(self):
        flow=Flow();flow.coordinator.async_refill_otps.side_effect=RuntimeError('secret must not be shown')
        result=await flow.async_step_otp_refill({'count':1})
        self.assertEqual(result['step_id'],'otp_refill_failed')
        self.assertNotIn('secret',str(result))
        self.assertEqual((await flow.async_step_otp_refill_failed({}))['type'],'menu')
        flow.coordinator.async_refill_otps.assert_awaited_once()
    async def test_read_failure_dismissal_does_not_retry(self):
        flow=Flow();flow.coordinator.async_get_remote_otps.side_effect=TimeoutError()
        self.assertEqual((await flow.async_step_otp_read())['errors']['base'],'otp_read_failed')
        self.assertEqual((await flow.async_step_otp_read({}))['type'],'menu')
        flow.coordinator.async_get_remote_otps.assert_awaited_once()
    async def test_invalid_count_does_not_write(self):
        flow=Flow()
        for count in [0,11,1.5,True]:
            self.assertEqual((await flow.async_step_otp_refill({'count':count}))['errors']['base'],'invalid_otp_count')
        flow.coordinator.async_refill_otps.assert_not_awaited()
    async def test_unloaded_and_empty_pool(self):
        self.assertEqual((await Flow(False).async_step_otp_read())['errors']['base'],'lock_not_loaded')
        flow=Flow();flow.coordinator.async_get_remote_otps.return_value=[]
        self.assertEqual((await flow.async_step_otp_read())['description_placeholders']['count'],'0')

if __name__=='__main__':unittest.main()
