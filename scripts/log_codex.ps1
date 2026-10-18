# Windows hook entry point: preserve UTF-8 stdin and use the local Python launcher.
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
$Payload = [Console]::In.ReadToEnd()
$Payload | & "$PSScriptRoot/_pyrun.cmd" "$PSScriptRoot/log_hook.py" --tool=codex
exit $LASTEXITCODE
