param(
    [string]$PythonPath = "python",
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$LogDir = Join-Path $ProjectRoot ".dev-logs"
$BackendStdout = Join-Path $LogDir "backend.stdout.log"
$BackendStderr = Join-Path $LogDir "backend.stderr.log"
$HealthUrl = "http://127.0.0.1:$BackendPort/health"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

try {
    & $PythonPath -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "missing dependencies"
    }
} catch {
    throw "Python 环境缺少 FastAPI/Uvicorn。请先激活后端环境，或通过 -PythonPath 指定解释器。"
}

$BackendProcess = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList @("-m", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", $BackendPort) `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $BackendStdout `
    -RedirectStandardError $BackendStderr `
    -WindowStyle Hidden `
    -PassThru

try {
    $BackendReady = $false
    for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
        if ($BackendProcess.HasExited) {
            break
        }
        try {
            $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 1
            if ($Response.StatusCode -eq 200) {
                $BackendReady = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $BackendReady) {
        $ErrorTail = if (Test-Path $BackendStderr) {
            (Get-Content $BackendStderr -Tail 30) -join [Environment]::NewLine
        } else {
            "未生成后端错误日志。"
        }
        throw "后端未能在 $HealthUrl 就绪。`n$ErrorTail"
    }

    Write-Host "后端已就绪: $HealthUrl" -ForegroundColor Green
    Write-Host "前端地址: http://localhost:$FrontendPort" -ForegroundColor Green
    Write-Host "按 Ctrl+C 同时停止前后端。"

    Push-Location $FrontendDir
    try {
        $env:VITE_BACKEND_URL = "http://127.0.0.1:$BackendPort"
        & npm.cmd run dev -- --port $FrontendPort
    } finally {
        Pop-Location
    }
} finally {
    if ($null -ne $BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force
    }
}
