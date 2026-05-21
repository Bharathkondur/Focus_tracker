$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".git")) {
    throw "This script must be run from inside the FocusTracker Git repository."
}

$hookDir = Join-Path $repoRoot ".git\hooks"
$hookPath = Join-Path $hookDir "post-commit"

New-Item -ItemType Directory -Force -Path $hookDir | Out-Null

$hook = @'
#!/bin/sh

# Auto-push after every successful commit.
# Disable for one commit/session with:
#   MOMENTUM_AUTO_PUSH=0 git commit ...

if [ "${MOMENTUM_AUTO_PUSH:-1}" = "0" ]; then
  echo "post-commit: auto-push skipped because MOMENTUM_AUTO_PUSH=0"
  exit 0
fi

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"
if [ -z "$branch" ]; then
  echo "post-commit: auto-push skipped because HEAD is detached"
  exit 0
fi

remote="$(git config --get "branch.${branch}.remote")"
merge_ref="$(git config --get "branch.${branch}.merge")"

if [ -z "$remote" ]; then
  remote="origin"
fi

if [ -z "$merge_ref" ]; then
  echo "post-commit: pushing ${branch} and setting upstream on ${remote}"
  git push -u "$remote" "$branch"
else
  echo "post-commit: pushing ${branch} to ${remote}"
  git push "$remote" "$branch"
fi
'@

Set-Content -Path $hookPath -Value $hook -Encoding ascii
git config --unset core.hooksPath 2>$null

Write-Host "Git hook installed: .git/hooks/post-commit"
Write-Host "Auto-push now runs after each successful commit."
Write-Host "Disable for a commit with: `$env:MOMENTUM_AUTO_PUSH='0'"
