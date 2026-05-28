# First-time setup of a ClaudeScore interview box

Do this once per device. After this, every interview is just `INTERVIEW_DAY.md`.

This guide assumes **Windows**. POSIX notes are inline where they differ.

> Want it automated? Run `scripts/setup-windows.ps1` as Administrator instead of doing steps 1–8 by hand. It also handles the config-dir isolation so candidates see no trace of your prior CLI history.

## 1. Install prerequisites

- **Python 3.10+** — <https://www.python.org/downloads/> (check "Add to PATH" during install).
- **Git** — <https://git-scm.com/download/win>.
- **Node.js 18+** — <https://nodejs.org/> (required by the Claude Code installer).

Verify:

```powershell
python --version    # >= 3.10
git --version
node --version
```

## 2. Install Claude Code

```powershell
npm install -g @anthropic-ai/claude-code
claude --version
```

Then sign in:

```powershell
claude
# follow the browser auth flow, then exit
```

## 3. Clone ClaudeScore

```powershell
New-Item -ItemType Directory -Path "$HOME\code" -Force | Out-Null
cd $HOME\code
git clone https://github.com/alisalmani-davinci/claude_score.git
cd claude_score
```

## 4. Install ClaudeScore in a venv

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e ".[judge]"
python -m claude_score --version
```

The `[judge]` extra installs the `anthropic` SDK so the optional LLM judge pass works. Skip it if you don't plan to use `--judge`.

## 5. Isolate Claude Code state from your personal account

You can sign in with your own Anthropic account on this box without your prior CLI history, memory, or settings ever appearing here. The trick is to tell Claude Code to use a **separate config directory**:

```powershell
$dir = Join-Path $HOME ".claude-interview"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
[Environment]::SetEnvironmentVariable("CLAUDE_CONFIG_DIR", $dir, "Machine")
```

Open a **fresh PowerShell** so the env var is picked up, then sign in:

```powershell
claude
# follow the browser auth flow; the token lands in $HOME\.claude-interview\
```

Anthropic billing flows through your account; everything Claude Code reads or writes on this box stays under `~/.claude-interview/` and never touches your real `~/.claude/`. ClaudeScore (which honours `CLAUDE_CONFIG_DIR`) reads from the same place automatically.

> Also: don't install Claude Desktop on this box, and don't sign claude.ai into any browser here. Both surface your synced web/desktop chat history; the CLI alone does not.

## 6. Env lockdown

Make sure nothing on this box silently suppresses transcript capture.

```powershell
# Must NOT be set:
[Environment]::GetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", "User")
[Environment]::GetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", "Machine")
# Both should print nothing. If either prints a value, clear it:
[Environment]::SetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $null, "User")
[Environment]::SetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $null, "Machine")
```

Bump transcript retention so a multi-week-old session isn't auto-deleted before you review it (writes to the isolated config dir from step 5):

```powershell
$settings = "$HOME\.claude-interview\settings.json"
if (-not (Test-Path $settings)) { "{}" | Set-Content $settings -Encoding UTF8 }
$json = Get-Content $settings -Raw | ConvertFrom-Json
$json | Add-Member -Force -NotePropertyName cleanupPeriodDays -NotePropertyValue 90
$json | ConvertTo-Json -Depth 5 | Set-Content $settings -Encoding UTF8
```

Verify everything:

```powershell
python -m claude_score interview preflight
```

You want `✓ Preflight clean — capture is unblocked.`

## 7. Optional: enable the LLM judge

If you want the `--judge` pass, set an Anthropic API key as a **machine-level** env var so it survives reboots and is available to the venv:

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "Machine")
```

Then close and reopen PowerShell so the new env is picked up.

## 8. Create the interview root

```powershell
New-Item -ItemType Directory -Path "$HOME\interviews" -Force | Out-Null
```

## 9. Make the candidate account a non-admin

Whoever the candidate logs in as should be a **standard user**, not an administrator. That way they can't change system env vars or global settings mid-session.

If the box is single-user, just don't share the admin password.

---

You're done. From here on, every interview is the runbook in `INTERVIEW_DAY.md`.
