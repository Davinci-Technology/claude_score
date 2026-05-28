# Automated Windows setup for a ClaudeScore interview box.
#
# Run as Administrator from PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\setup-windows.ps1
#
# What it does:
#   * Verifies Python, git, and Node are installed (does NOT install them — see docs/SETUP.md if any are missing).
#   * Installs the Claude Code CLI globally via npm.
#   * Clones claude_score into $HOME\code\claude_score (or pulls if it already exists).
#   * Creates a venv there, installs the package + the [judge] extra.
#   * Isolates Claude Code state under $HOME\.claude-interview\ via CLAUDE_CONFIG_DIR
#     so the operator's signed-in account does NOT expose any prior CLI history
#     on this box. Sign-in (run manually after this script) writes its token there.
#   * Env lockdown: clears CLAUDE_CODE_SKIP_PROMPT_HISTORY at both scopes,
#     ensures the new settings.json has cleanupPeriodDays >= 90.
#   * Creates ~/interviews/.
#   * Runs `claude_score interview preflight` so you can see the final state.
#
# Idempotent — safe to re-run.

$ErrorActionPreference = "Stop"

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "  ✗ $cmd not on PATH. $hint" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ $cmd" -ForegroundColor Green
}

Write-Host "`n=== 1. Checking prerequisites ===" -ForegroundColor Cyan
Need "python" "Install Python 3.10+ from https://www.python.org/downloads/ (check 'Add to PATH')."
Need "git"    "Install Git from https://git-scm.com/download/win."
Need "node"   "Install Node.js 18+ from https://nodejs.org/."
Need "npm"    "Install Node.js 18+ from https://nodejs.org/."

Write-Host "`n=== 2. Installing Claude Code CLI ===" -ForegroundColor Cyan
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Host "  claude already installed: $((claude --version) 2>&1)"
} else {
    npm install -g @anthropic-ai/claude-code
    Write-Host "  installed: $((claude --version) 2>&1)"
}

Write-Host "`n=== 3. Cloning / updating claude_score ===" -ForegroundColor Cyan
$codeDir = Join-Path $HOME "code"
$repoDir = Join-Path $codeDir "claude_score"
if (-not (Test-Path $codeDir)) { New-Item -ItemType Directory -Path $codeDir | Out-Null }
if (Test-Path (Join-Path $repoDir ".git")) {
    Push-Location $repoDir
    git pull --ff-only
    Pop-Location
} else {
    git clone https://github.com/alisalmani-davinci/claude_score.git $repoDir
}

Write-Host "`n=== 4. Creating venv and installing ===" -ForegroundColor Cyan
Push-Location $repoDir
if (-not (Test-Path ".venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip --quiet
pip install -e ".[judge]" --quiet
Write-Host "  installed: $((python -m claude_score --version) 2>&1)"
Pop-Location

Write-Host "`n=== 5. Isolating Claude Code state to a separate config dir ===" -ForegroundColor Cyan
# Why: lets you sign in with your own Anthropic account for billing without
# any of your personal CLI history, memory, or settings being visible on this
# box. Everything Claude Code reads/writes goes to $HOME\.claude-interview\
# instead of $HOME\.claude\.
$interviewConfigDir = Join-Path $HOME ".claude-interview"
if (-not (Test-Path $interviewConfigDir)) {
    New-Item -ItemType Directory -Path $interviewConfigDir | Out-Null
    Write-Host "  created $interviewConfigDir"
} else {
    Write-Host "  $interviewConfigDir already exists ✓" -ForegroundColor Green
}
[Environment]::SetEnvironmentVariable("CLAUDE_CONFIG_DIR", $interviewConfigDir, "Machine")
$env:CLAUDE_CONFIG_DIR = $interviewConfigDir  # so the preflight step at the end of this script picks it up
Write-Host "  set CLAUDE_CONFIG_DIR=$interviewConfigDir (Machine scope)" -ForegroundColor Yellow
Write-Host "  NOTE: open a fresh shell after this script before signing in with 'claude'" -ForegroundColor Yellow

Write-Host "`n=== 6. Env lockdown ===" -ForegroundColor Cyan
foreach ($scope in @("User", "Machine")) {
    $v = [Environment]::GetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $scope)
    if ($v) {
        [Environment]::SetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $null, $scope)
        Write-Host "  cleared CLAUDE_CODE_SKIP_PROMPT_HISTORY ($scope)" -ForegroundColor Yellow
    } else {
        Write-Host "  CLAUDE_CODE_SKIP_PROMPT_HISTORY not set ($scope) ✓" -ForegroundColor Green
    }
}

$settingsPath = Join-Path $interviewConfigDir "settings.json"
if (Test-Path $settingsPath) {
    try { $json = Get-Content $settingsPath -Raw | ConvertFrom-Json } catch { $json = [PSCustomObject]@{} }
} else {
    $json = [PSCustomObject]@{}
}
$current = if ($json.PSObject.Properties.Match("cleanupPeriodDays")) { $json.cleanupPeriodDays } else { $null }
if (-not $current -or $current -lt 90) {
    $json | Add-Member -Force -NotePropertyName cleanupPeriodDays -NotePropertyValue 90
    $json | ConvertTo-Json -Depth 8 | Set-Content $settingsPath -Encoding UTF8
    Write-Host "  set cleanupPeriodDays=90 in $settingsPath" -ForegroundColor Yellow
} else {
    Write-Host "  cleanupPeriodDays already $current ✓" -ForegroundColor Green
}

Write-Host "`n=== 7. Creating interview root ===" -ForegroundColor Cyan
$interviewRoot = Join-Path $HOME "interviews"
if (-not (Test-Path $interviewRoot)) {
    New-Item -ItemType Directory -Path $interviewRoot | Out-Null
    Write-Host "  created $interviewRoot"
} else {
    Write-Host "  $interviewRoot already exists ✓" -ForegroundColor Green
}

Write-Host "`n=== 8. Preflight ===" -ForegroundColor Cyan
Push-Location $repoDir
. .\.venv\Scripts\Activate.ps1
python -m claude_score interview preflight
Pop-Location

Write-Host "`nSetup finished." -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a FRESH PowerShell so the new CLAUDE_CONFIG_DIR is picked up."
Write-Host "  2. Run 'claude' and sign in with your Anthropic account. The token lands in"
Write-Host "     $interviewConfigDir — none of your prior CLI history follows you to this box."
Write-Host "  3. See docs/INTERVIEW_DAY.md for the per-candidate workflow."
