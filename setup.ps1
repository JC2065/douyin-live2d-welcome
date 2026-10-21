param([switch]$AcceptLive2DTerms)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $AcceptLive2DTerms) {
    Write-Host 'Live2D Core and sample models have separate licenses. Review:'
    Write-Host 'https://www.live2d.com/en/sdk/license/'
    Write-Host 'https://www.live2d.com/en/learn/sample/'
    throw 'After reviewing the terms, run: .\setup.ps1 -AcceptLive2DTerms'
}
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Force web/assets,web/models,data/audio,vendor | Out-Null
if (-not (Test-Path 'vendor/pixi-live2d-display')) {
    git clone https://github.com/guansss/pixi-live2d-display.git vendor/pixi-live2d-display
    if ($LASTEXITCODE -ne 0) { throw 'Model repository download failed.' }
    git -C vendor/pixi-live2d-display checkout 31317b37d5e22955a44d5b11f37f421e94a11269
    if ($LASTEXITCODE -ne 0) { throw 'Pinned model version unavailable.' }
}
if (-not (Test-Path 'web/models/haru')) {
    Copy-Item vendor/pixi-live2d-display/test/assets/haru web/models/haru -Recurse
}
$modelPath = 'web/models/haru/haru_greeter_t03.model3.json'
$modelData = Get-Content -Raw $modelPath | ConvertFrom-Json
foreach ($motion in $modelData.FileReferences.Motions.Tap) { $motion.PSObject.Properties.Remove('Sound') }
$modelData | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $modelPath
Invoke-WebRequest https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/dist/browser/pixi.min.js -OutFile web/assets/pixi.min.js
Invoke-WebRequest https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js -OutFile web/assets/cubism4.min.js
Invoke-WebRequest https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js -OutFile web/assets/live2dcubismcore.min.js
Invoke-WebRequest https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber/main/LICENSE-Live2D.md -OutFile web/models/LICENSE-Live2D.md
Write-Host 'Setup complete. Run start.cmd.'
