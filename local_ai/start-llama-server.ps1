$ErrorActionPreference = "Stop"
if (-not $env:LLAMA_SERVER_BIN) { throw "Set LLAMA_SERVER_BIN to the local llama-server executable." }
if (-not $env:UNEXPECTED_LOCAL_MODEL_PATH) { throw "Set UNEXPECTED_LOCAL_MODEL_PATH to a reviewed local GGUF file." }
if (-not $env:UNEXPECTED_LOCAL_MODEL) { throw "Set UNEXPECTED_LOCAL_MODEL to the local model alias." }
if (-not (Test-Path -LiteralPath $env:LLAMA_SERVER_BIN -PathType Leaf)) { throw "llama-server executable not found." }
if (-not (Test-Path -LiteralPath $env:UNEXPECTED_LOCAL_MODEL_PATH -PathType Leaf)) { throw "Local model file not found." }
$resolved = (Resolve-Path -LiteralPath $env:UNEXPECTED_LOCAL_MODEL_PATH).Path
& $env:LLAMA_SERVER_BIN --model $resolved --alias $env:UNEXPECTED_LOCAL_MODEL --host 127.0.0.1 --port 8080
exit $LASTEXITCODE
