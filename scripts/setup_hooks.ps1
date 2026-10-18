# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $RepoRoot
$HookFile = git -c "safe.directory=$($RepoRoot.Replace('\', '/'))" rev-parse --git-path hooks/pre-push
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Git hooks directory.' }
$HookBody = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'hooks/pre-push')).Replace("`r`n", "`n")
[IO.Directory]::CreateDirectory((Split-Path ([IO.Path]::GetFullPath($HookFile)))) | Out-Null
[IO.File]::WriteAllText([IO.Path]::GetFullPath($HookFile), $HookBody, [Text.UTF8Encoding]::new($false))
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
