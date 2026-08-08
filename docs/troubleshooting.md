# Troubleshooting

## PowerShell blocks npm.ps1

Use `npm.cmd` instead of `npm`.

## API imports fail

Activate the project virtual environment or run commands through `.venv/Scripts/python.exe` on Windows.

## Simulator says Core reconnecting

Confirm the API is running on `127.0.0.1:8765` and that `GET /api/health` succeeds.
