$ErrorActionPreference = "Stop"

$githubCli = Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"
$npxCli = Join-Path $env:ProgramFiles "nodejs\npx.cmd"

$serverCli = Join-Path $env:USERPROFILE 'bin\github-mcp-server.exe'

if (-not (Test-Path -LiteralPath $githubCli)) {
    [Console]::Error.WriteLine("GitHub CLI was not found at $githubCli")
    exit 1
}

if (-not (Test-Path -LiteralPath $npxCli)) {
    [Console]::Error.WriteLine("npx was not found at $npxCli")
    exit 1
}

& $githubCli auth status --hostname github.com *> $null
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("GitHub CLI is not authenticated. Run: gh auth login")
    exit 1
}

$githubToken = (& $githubCli auth token --hostname github.com).Trim()
if ([string]::IsNullOrWhiteSpace($githubToken)) {
    [Console]::Error.WriteLine("GitHub CLI did not return a token.")
    exit 1
}

$env:GITHUB_PERSONAL_ACCESS_TOKEN = $githubToken
$serverExitCode = 1
try {
    if (Test-Path -LiteralPath $serverCli) {
        & $serverCli stdio
        $serverExitCode = $LASTEXITCODE
    }
    else {
    & $npxCli -y @modelcontextprotocol/server-github
    $serverExitCode = $LASTEXITCODE
    }
}
finally {
    Remove-Item Env:GITHUB_PERSONAL_ACCESS_TOKEN -ErrorAction SilentlyContinue
    $githubToken = $null
}

exit $serverExitCode
