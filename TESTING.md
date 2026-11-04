# OTP test build

Use beta `v1.0.2-beta.2` from branch `feat/otp-ui`: it includes the tools, pool
reading, refill, and native options UI. Timed PIN generation is not included.

## Install through HACS

Open your fork in HACS, choose Redownload, and select v1.0.2-beta.2 (enable
prereleases if needed). Restart Home Assistant, then open Settings → Devices &
services → Atomberg Lock → Configure. Read OTP pool and Refill OTPs are in that
menu. Results display all returned slots and codes. Start with a one-code refill.
The original connection-settings form is available under Connection settings.
The Developer Tools procedures below remain available as an alternative.

The owner has confirmed hardware refill and read-back through Developer Tools.
For this beta, verify the UI and then the first/second-use code behavior.

## Install manually

1. Back up your existing `/config/custom_components/atomberg_lock` folder
   somewhere outside `custom_components`.
2. Extract `atomberg-lock-test.zip` on your computer. Replace the existing
   `/config/custom_components/atomberg_lock` folder with the archive's
   `custom_components/atomberg_lock` folder. Copy the complete folder, including
   the new `otp.py`, `services.py`, and `services.yaml` files.
3. Restart Home Assistant. Keep your existing configured integration and keys;
   do not delete the integration or reset the lock. Avoid a HACS update during
   this test, as it would replace the manual test build.
4. Close the Atomberg iPhone app so Home Assistant can connect to the lock.

## Read first

In **Developer Tools → Actions**, select **Atomberg Lock: Read remote OTP pool
(experimental)**. Select your lock in the **Lock** field and perform the action
as an administrator. Save the returned slot numbers privately as a baseline.
Codes appear in response data, not device-page buttons or entity states.

YAML equivalent (use the UI selector to obtain your config entry ID):

```yaml
action: atomberg_lock.get_remote_otps
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
```

The read action returns existing codes. Repeating it can return the same codes;
it does not reserve one, mark it used, or generate a new code. Do not publish
response data or automation traces containing actual codes.

## Refill one code

Choose **Atomberg Lock: Refill OTP pool (experimental)**, select your lock, and
set **Number of codes** to **1**. This writes to the lock. The response should
return exactly one new slot and code after acknowledgement and read-back.

```yaml
action: atomberg_lock.refill_otps
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
  count: 1
```

Read the pool again and check for the returned slot/code. If refill fails, read
the pool before retrying: a code may have been written before a timeout. Do not
set up automatic retries or scheduled refills during validation.

## Hardware check

With the door open and mechanical key available, enter the newly returned code
on the lock. Note whether it unlocks, allow it to relock, and try that same code
again. Report whether the first attempt succeeds and the second is rejected.
Read the pool once more and note whether that slot remains or disappears.
Do not include the code itself in your report.

Also verify that Get Battery and normal unlock still work. The integration's
new refill does not synchronize with Atomberg's server/app pool. Firmware
capacity, expiry, and one-time semantics still require hardware validation.

## If there is an error

Stop repeated writes. Share the error message and the relevant Home Assistant
log entry, removing codes, keys, MAC addresses, and decrypted payloads. Include
which action failed and whether a new slot appeared after reading the pool.

## Roll back

Restore your backed-up integration folder and restart Home Assistant. This
rolls back the software; it does not remove codes already written to the lock.
Do not delete unfamiliar credentials to undo a failed test.
