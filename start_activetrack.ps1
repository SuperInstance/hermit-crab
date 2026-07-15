$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptPath
Write-Host "Starting ActiveTrack..."
python3 activetrack.py
