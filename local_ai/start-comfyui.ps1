$ErrorActionPreference = "Stop"
if (-not $env:COMFYUI_HOME) { throw "Set COMFYUI_HOME to the local ComfyUI checkout." }
if (-not $env:COMFYUI_PYTHON) { throw "Set COMFYUI_PYTHON to the local Python executable." }
$main = Join-Path $env:COMFYUI_HOME "main.py"
if (-not (Test-Path -LiteralPath $main -PathType Leaf)) { throw "ComfyUI main.py not found." }
if (-not (Test-Path -LiteralPath $env:COMFYUI_PYTHON -PathType Leaf)) { throw "ComfyUI Python executable not found." }
Push-Location $env:COMFYUI_HOME
try {
    & $env:COMFYUI_PYTHON main.py --listen 127.0.0.1 --port 8188 --offline --disable-partner-nodes
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
