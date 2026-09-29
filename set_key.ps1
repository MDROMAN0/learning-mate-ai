$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$envPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $PSScriptRoot '.env.example') $envPath }
Write-Host ""
Write-Host "Gemini API key paste koro (right-click), tarpor Enter chapo. (Screen-e key dekhabe na)" -ForegroundColor Yellow
$sec = Read-Host "Key" -AsSecureString
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if ($key.Length -lt 20) { Write-Host "Key paoa jayni. Abar set_key.bat chalao." -ForegroundColor Red; Read-Host "Enter chapo"; exit 1 }
$old = Get-Content $envPath
$pwLine = $old | Where-Object { $_ -match '^APP_PASSWORD=\S+' } | Select-Object -First 1
if ($pwLine) { $pw = $pwLine.Substring(13) } else {
  $chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  $bytes = New-Object byte[] 14
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $pw = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}
$rest = $old | Where-Object { $_ -notmatch '^(LLM_API_KEY|APP_PASSWORD)=' }
$lines = @("LLM_API_KEY=$key") + $rest + @("APP_PASSWORD=$pw")
[IO.File]::WriteAllLines($envPath, [string[]]$lines)
Write-Host ""
Write-Host "Key save hoyeche (.env)." -ForegroundColor Green
Write-Host "APP_PASSWORD = $pw   <-- eta save kore rakho" -ForegroundColor Cyan
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and ($py.Source -notmatch 'WindowsApps')) { Write-Host ("Python: " + (& python --version 2>&1)) } else { Write-Host "Python: NOT INSTALLED" -ForegroundColor Red }
Write-Host ""
Read-Host "Shesh. Enter chapo, tarpor Claude-ke 'done' likho"
