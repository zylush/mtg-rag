[CmdletBinding()]
param(
    [string]$ProjectRoot = "E:\Vcode\Pandas\MTG-RAG"
)

$ErrorActionPreference = "Stop"

$gcloudCli = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$firebaseCli = Join-Path $env:APPDATA "npm\firebase.cmd"
$githubCli = Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"
$codexCli = (Get-Command codex -ErrorAction Stop).Source

foreach ($requiredPath in @($gcloudCli, $firebaseCli, $githubCli, $codexCli, $ProjectRoot)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path was not found: $requiredPath"
    }
}

$activeGoogleAccount = @(
    & $gcloudCli auth list --filter="status:ACTIVE" --format="value(account)" 2>$null
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

if ($activeGoogleAccount.Count -eq 0) {
    & $gcloudCli init
    if ($LASTEXITCODE -ne 0) {
        throw "Google Cloud initialization failed."
    }
}

$firebaseLoginStatus = (& $firebaseCli login:list 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0 -or $firebaseLoginStatus -notmatch "Logged in as") {
    & $firebaseCli login
    if ($LASTEXITCODE -ne 0) {
        throw "Firebase login failed."
    }
}

& $githubCli auth status --hostname github.com *> $null
if ($LASTEXITCODE -ne 0) {
    & $githubCli auth login --hostname github.com --web --git-protocol https
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub login failed."
    }
}

$githubToken = (& $githubCli auth token --hostname github.com).Trim()
if ([string]::IsNullOrWhiteSpace($githubToken)) {
    throw "GitHub CLI did not return a token."
}

$env:GITHUB_PERSONAL_ACCESS_TOKEN = $githubToken
try {
    Set-Location -LiteralPath $ProjectRoot
    & $codexCli
}
finally {
    Remove-Item Env:GITHUB_PERSONAL_ACCESS_TOKEN -ErrorAction SilentlyContinue
    $githubToken = $null
}
