$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$ready = $false
try { $status = Invoke-RestMethod 'http://127.0.0.1:18765/api/status' -TimeoutSec 2; $ready = $status.cooldown -eq 60 } catch {}
if (-not $ready) {
    $process = Start-Process -FilePath $pythonExe -ArgumentList 'app.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'data/server.out.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data/server.err.log')
    $process.Id | Set-Content (Join-Path $PSScriptRoot 'data/server.pid')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { Invoke-RestMethod 'http://127.0.0.1:18765/api/status' -TimeoutSec 1 | Out-Null; $ready = $true; break } catch {}
    }
}
if (-not $ready) { throw '服务启动失败，请查看 data/server.err.log' }
Start-Process 'http://127.0.0.1:18765'
