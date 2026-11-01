param([string]$Distro = 'Ubuntu-22.04')
# wsl/docker write progress to stderr; stderr must not abort the script.
$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogRoot = Join-Path $ProjectRoot '.data'
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
function Test-Docker {
    $probe = & wsl -d $Distro -u root --exec docker info --format '{{.OSType}}' 2>&1
    return ($LASTEXITCODE -eq 0 -and ($probe -match 'linux'))
}
if (Test-Docker) { exit 0 }
Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d',$Distro,'-u','root','--exec','dockerd') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogRoot 'dockerd.log') -RedirectStandardError (Join-Path $LogRoot 'dockerd-error.log') | Out-Null
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Seconds 1
    if (Test-Docker) { exit 0 }
}
Write-Error 'Docker failed to start. Inspect .data/dockerd-error.log.'
exit 1
