# Capturing missing Atomberg features

OTP refill, remote OTP generation, and credential management are not implemented
in the integration. Command identifiers and payloads must first be established
from official-app traces. Do not replay encrypted session packets directly.

For each feature, save a separate iPhone PacketLogger trace:

1. Force-close the Atomberg app to end its Bluetooth session.
2. Start **New iOS Trace** in PacketLogger before reopening the app.
3. Open Atomberg, connect to the lock, and perform the feature once.
4. Note the action, approximate time, settings entered, and result shown by the app.
5. Stop and save the trace locally. No lock reset is required.

A refill trace must include the connection handshake, not only the refill itself.
For remote OTP generation, also note whether Bluetooth was connected. Bluetooth
captures cannot reveal server-only API calls.

Install `tools/requirements.txt` in a virtual environment, then run:

```sh
python tools/analyze_capture.py '/path/to/capture.pklg'
```

The analyser reads the project `.env` without sourcing it and prints only command
metadata, never keys, PINs, or decrypted payloads. It uses the upstream HSJ frame
decoder and supports PacketLogger byte orders and ACL reassembly. A capture with
all frames undecoded commonly lacks the session handshake; it is not evidence
that the stored pairing key is wrong. Unknown commands require manual validation
of payloads and acknowledgements before adding any live controls.

Keep raw traces and `.env` private; traces can contain access credentials.

Parser checks:

```sh
python -m unittest discover -s tools -p 'test_*.py'
```
