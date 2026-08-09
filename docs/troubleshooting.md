# Troubleshooting

## PowerShell blocks npm.ps1

Use `npm.cmd` instead of `npm`.

## API imports fail

Activate the project virtual environment or run commands through `.venv/Scripts/python.exe` on Windows.

## Simulator says Core reconnecting

Confirm the API is running on `127.0.0.1:8765` and that `GET /api/health` succeeds.

## A reply is shown but never spoken

The simulator speaks through the browser, which can only use voices the host
operating system installed. A default Windows install ships English only, so Bengali,
Hindi, Chinese and most other replies have no voice and are displayed silently. List
what your system actually has:

```bash
powershell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | Select-Object Name, Culture"
```

Manny refuses to read Bengali script with an English voice, because that produces
noise rather than speech. Instead it asks the device to synthesise the reply, which is
the same eSpeak NG path the Pi speaks with and covers far more languages than any
desktop voice set. Install eSpeak NG locally and set `MANNY_TTS_BACKEND=espeak_ng` in
`.env` to enable it. An `espeak-ng` on PATH is found wherever it lives; set
`MANNY_ESPEAK_NG_BINARY` only if it is somewhere PATH does not reach.

Two messages distinguish the remaining cases. "This device has no local speech
synthesis configured" means `MANNY_TTS_BACKEND` is still `mock`. "Local speech
synthesis is configured but did not answer" means it is set to `espeak_ng` but the
binary is missing or failed — check that the command below prints audio bytes:

```bash
espeak-ng -v bn --stdout "আপনার বাজেট" | wc -c
```
