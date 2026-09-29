# Claude job runner: runs jobs\*.cmd files (written by Claude) one by one, logs to jobs\*.log.
# Close this window to stop it.
Set-Location $PSScriptRoot
$jobs = Join-Path $PSScriptRoot 'jobs'
New-Item -ItemType Directory -Force $jobs | Out-Null
$host.UI.RawUI.WindowTitle = 'Claude runner (ytrag) - bondho korle kaj thambe'
Write-Host 'Claude runner cholche. Ei window khola rakho. (Bondho korle Claude PC-te kaj korte parbe na)' -ForegroundColor Green
while ($true) {
  Get-ChildItem $jobs -Filter *.cmd | Sort-Object Name | ForEach-Object {
    $log = [IO.Path]::ChangeExtension($_.FullName, '.log')
    Write-Host ((Get-Date -Format 'HH:mm:ss') + ' running ' + $_.Name)
    $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
    & cmd.exe /c "`"$($_.FullName)`" > `"$log`" 2>&1"
    Add-Content $log ("`r`n===EXIT " + $LASTEXITCODE + "===")
    Move-Item $_.FullName ($_.FullName + '.done') -Force
  }
  Start-Sleep -Seconds 3
}
