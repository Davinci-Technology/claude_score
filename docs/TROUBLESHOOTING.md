# Troubleshooting

## Preflight reports `CLAUDE_CODE_SKIP_PROMPT_HISTORY is set`

That env var suppresses the transcript — meaning the whole tool has nothing to read. Clear it for both User and Machine scope:

```powershell
[Environment]::SetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $null, "User")
[Environment]::SetEnvironmentVariable("CLAUDE_CODE_SKIP_PROMPT_HISTORY", $null, "Machine")
```

Open a new shell and re-run `python -m claude_score interview preflight`.

## Preflight reports `claude command not found on PATH`

Either Claude Code wasn't installed (`npm install -g @anthropic-ai/claude-code`) or the shell hasn't picked up the new PATH yet. Close all terminals and open a fresh one.

## Preflight warns `cleanupPeriodDays=30`

Transcripts will auto-delete after 30 days by default. Bump it (writes to the isolated config dir, not your personal `~/.claude/`):

```powershell
$settings = "$HOME\.claude-interview\settings.json"
$json = Get-Content $settings -Raw | ConvertFrom-Json
$json | Add-Member -Force -NotePropertyName cleanupPeriodDays -NotePropertyValue 90
$json | ConvertTo-Json -Depth 5 | Set-Content $settings -Encoding UTF8
```

## `interview finish` can't find the candidate's transcripts after fresh setup

Most likely cause: `CLAUDE_CONFIG_DIR` wasn't set in the shell where the candidate ran `claude`, so their transcript went to `~/.claude/projects/` instead of `~/.claude-interview/projects/`. Check:

```powershell
echo $env:CLAUDE_CONFIG_DIR
[Environment]::GetEnvironmentVariable("CLAUDE_CONFIG_DIR", "Machine")
```

If the Machine value is set but the current shell shows nothing, the candidate ran `claude` in a shell opened *before* the setup script. Open a fresh shell, then either re-run the analysis pointing at the right dir (`python -m claude_score analyze <munged-name>`) or hand-copy the JSONL into the candidate's `transcripts/` folder and re-run `interview finish`.

## `interview finish` says "No Claude Code transcripts found whose cwd matches ..."

The candidate ran `claude` from a different directory than the one ClaudeScore created. Find their session:

```powershell
python -m claude_score list
```

The most recently modified project at the top is likely theirs. Then either:

- Copy the JSONL(s) into the candidate folder yourself:
  ```powershell
  Copy-Item "$HOME\.claude\projects\<munged-name>\*.jsonl" "$HOME\interviews\<slug>\transcripts\"
  python -m claude_score interview finish "<Name>"
  ```
- Or analyze that project directly:
  ```powershell
  python -m claude_score analyze "<munged-name>" --candidate "<Name>" --html report.html
  ```

## `interview finish --judge` fails with auth error

The `--judge` pass needs `ANTHROPIC_API_KEY` set in the env where Python runs. Set it machine-level and reopen the shell:

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "Machine")
```

Re-run finish without `--judge` first to get the deterministic scorecard, then run with `--judge` once auth is sorted; the report just gets richer.

## `pip install -e ".[judge]"` complains about the `[judge]` extra

You're on an older pip. Upgrade and retry:

```powershell
python -m pip install --upgrade pip
pip install -e ".[judge]"
```

## A candidate's session is empty / has no prompts

Either they didn't actually run `claude` (look in `$HOME\.claude\projects\` for *any* recent activity), or they ran with `--no-session-persistence`. The session can't be reconstructed in that case — flag it to the operator before grading.

## The report HTML looks unstyled

That means `jinja2` couldn't load the template. Reinstall the package (the template ships in `claude_score/templates/`):

```powershell
pip install -e . --force-reinstall --no-deps
```

## "Old vibepulse dir is locked" / Windows file-in-use errors

Unrelated to a candidate session — that's a dev-machine leftover from the rename to ClaudeScore. Close any editor or terminal with a handle in the affected dir and delete by hand. Doesn't affect the interview box.
