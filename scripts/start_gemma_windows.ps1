$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$server = Join-Path $repositoryRoot 'data\llama-b9637\llama-server.exe'
$model = Join-Path $repositoryRoot 'data\models\gemma-3-1b-it-Q4_K_M.gguf'
$logRoot = Join-Path $repositoryRoot 'data\logs'

if (-not (Test-Path $server) -or -not (Test-Path $model)) {
    throw 'Run scripts\install_gemma_windows.ps1 first.'
}
if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'Local Gemma is already listening on 127.0.0.1:8080.'
    exit 0
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$arguments = @(
    '-m', $model,
    '--alias', 'gemma-3-1b-it',
    '--host', '127.0.0.1',
    '--port', '8080',
    '--ctx-size', '4096',
    '--threads', '4',
    '--parallel', '1',
    '--no-webui'
)
$process = Start-Process -FilePath $server -ArgumentList $arguments `
    -WorkingDirectory (Split-Path $server) -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logRoot 'llama-server.out.log') `
    -RedirectStandardError (Join-Path $logRoot 'llama-server.err.log')

$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 2
        if ($health.status -eq 'ok') {
            Set-Content -LiteralPath (Join-Path $repositoryRoot 'data\llama-server.pid') -Value $process.Id
            Write-Host "Local Gemma is ready (PID $($process.Id))."
            exit 0
        }
    } catch {
        if ($process.HasExited) { throw 'llama.cpp exited before becoming ready.' }
    }
} while ((Get-Date) -lt $deadline)

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
throw 'Local Gemma did not become ready within 30 seconds.'
