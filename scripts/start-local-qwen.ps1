param(
    [ValidateSet(4096, 8192, 16384)]
    [int]$ContextSize = 8192,
    [ValidateSet("Q8_0", "Q4_K_M-requant")]
    [string]$Quantization = "Q8_0"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimePath = Join-Path $projectRoot ".local-archive/models-cleanup-20261011-3UZ0qB/llama-b11514-no-prefetch-cuda13.0/llama-server.exe"
$modelPath = Join-Path $projectRoot "models/Qwen3.5-9B-Q8_0/Qwen_Qwen3.5-9B-Q8_0.gguf"
if ($Quantization -eq "Q4_K_M-requant") {
    $modelPath = Join-Path $projectRoot "models/Qwen3.5-9B-Q4_K_M-requant/Qwen3.5-9B-Q4_K_M-requant.gguf"
}
$modelAlias = "Qwen3.5-9B-$Quantization"

foreach ($requiredPath in @($runtimePath, $modelPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required local file is missing: $requiredPath"
    }
}
if ([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        Where-Object { $_.Port -eq 8080 }) {
    throw "Port 8080 is already in use. Stop its server before launching Qwen."
}

$serverArguments = @(
    "--model", ('"' + $modelPath + '"'), "--alias", $modelAlias,
    "--host", "127.0.0.1", "--port", "8080", "--ctx-size", "$ContextSize", "--parallel", "1",
    "--n-gpu-layers", "99", "--fit", "off", "--flash-attn", "on",
    "--cache-type-k", "f16", "--cache-type-v", "f16", "--cache-ram", "0",
    "--load-mode", "mmap", "--no-host", "--no-repack", "--no-warmup",
    "--batch-size", "128", "--ubatch-size", "16", "--threads", "4", "--threads-batch", "4",
    "--jinja", "--reasoning", "off", "--reasoning-budget", "0",
    "--no-context-shift", "--no-webui", "--no-slots", "--cors-origins", "http://127.0.0.1:8080"
)
Write-Host "$modelAlias | llama.cpp b11514 | http://127.0.0.1:8080 | context $ContextSize"
Write-Host "Keep this terminal open while using the chat."
$serverProcess = Start-Process -FilePath $runtimePath -ArgumentList $serverArguments -NoNewWindow -Wait -PassThru
exit $serverProcess.ExitCode
