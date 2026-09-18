param(
    [string]$Version = 'dev'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$appDir = $PSScriptRoot
Set-Location -LiteralPath $appDir
$python = Join-Path $appDir '.venv-translation\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Build environment was not found. Run setup.bat on a PC with Python 3 first.'
}

& $python -m pip install -r (Join-Path $appDir 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }

& $python -m unittest discover -s (Join-Path $appDir 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }

& $python -m PyInstaller --clean --noconfirm (Join-Path $appDir 'translation_server.spec')
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }

$packageName = "stream-tools-windows-$Version"
$packageDir = Join-Path $appDir "dist\$packageName"
$archivePath = Join-Path $appDir "dist\$packageName.zip"
if ((Test-Path -LiteralPath $packageDir) -or (Test-Path -LiteralPath $archivePath)) {
    throw "Package output already exists: $packageName. Remove it or use a different version."
}
New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
Copy-Item (Join-Path $appDir 'dist\translation_server.exe') $packageDir
Copy-Item (Join-Path $appDir 'haishin.bat') $packageDir
Copy-Item (Join-Path $appDir 'haishin_launcher.ps1') $packageDir
Copy-Item (Join-Path $appDir 'setup.bat') $packageDir
Copy-Item (Join-Path $appDir 'README.md') $packageDir
Copy-Item (Join-Path $appDir 'config.example.json') $packageDir
Compress-Archive -Path (Join-Path $packageDir '*') -DestinationPath $archivePath -Force
Write-Host "[BUILT] $archivePath"
