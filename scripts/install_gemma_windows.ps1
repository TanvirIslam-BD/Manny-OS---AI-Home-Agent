param(
    [switch]$AcceptLicense
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dataRoot = Join-Path $repositoryRoot 'data'
$runtimeRoot = Join-Path $dataRoot 'llama-b9637'
$archivePath = Join-Path $dataRoot 'llama-b9637.zip'
$modelRoot = Join-Path $dataRoot 'models'
$modelPath = Join-Path $modelRoot 'gemma-3-1b-it-Q4_K_M.gguf'
$runtimeUrl = 'https://github.com/ggml-org/llama.cpp/releases/download/b9637/llama-b9637-bin-win-cpu-x64.zip'
$runtimeSha256 = 'f7783c2b8c007f95e710ac40f26a24861a80b603b0b739fc54d7c926a4716c1e'
$modelUrl = 'https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf'
$modelSha256 = '8ccc5cd1f1b3602548715ae25a66ed73fd5dc68a210412eea643eb20eb75a135'

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Manny requires 64-bit Windows for the pinned llama.cpp runtime.'
}
if (-not $AcceptLicense) {
    Write-Host 'Review the Gemma license and prohibited-use policy: https://ai.google.dev/gemma/terms'
    $answer = Read-Host 'Download and install the local model? [y/N]'
    if ($answer -notin @('y', 'Y')) { exit 0 }
}

New-Item -ItemType Directory -Force -Path $dataRoot, $modelRoot | Out-Null

if (-not (Test-Path (Join-Path $runtimeRoot 'llama-server.exe'))) {
    & curl.exe -fL --retry 3 --output $archivePath $runtimeUrl
    if ($LASTEXITCODE -ne 0) { throw 'llama.cpp download failed.' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant() -ne $runtimeSha256) {
        throw 'llama.cpp archive checksum mismatch.'
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimeRoot -Force
}

if (-not (Test-Path $modelPath)) {
    $downloadPath = "$modelPath.download"
    & curl.exe -fL --retry 3 --output $downloadPath $modelUrl
    if ($LASTEXITCODE -ne 0) { throw 'Gemma model download failed.' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $downloadPath).Hash.ToLowerInvariant() -ne $modelSha256) {
        throw 'Gemma model checksum mismatch.'
    }
    Move-Item -LiteralPath $downloadPath -Destination $modelPath -Force
}

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $modelPath).Hash.ToLowerInvariant() -ne $modelSha256) {
    throw 'Installed Gemma model checksum mismatch. Remove the model and run this installer again.'
}

Write-Host 'Local Gemma runtime installed and verified. Run scripts\start_gemma_windows.ps1.'
