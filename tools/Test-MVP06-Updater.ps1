<#
MVP06-Plus: the Launcher's updater, tried on your private test release (never the public one).

  1. publishes the test release that Make-MVP06-Test-Release.cmd made (a draft in your PRIVATE MVP06-Plus-test
     repository), so the updater can see it. It stays private: only you can see that repository.
  2. copies the test build's program files (not the game files or saves) from Downloads\MVP06-Plus-Beta-2 to
     Downloads\MVP06-Plus-updater-test, so your real install is never touched
  3. opens that copy's Launcher pretending to be Beta 1, reading releases from MVP06-Plus-test with your GitHub
     sign-in. Settings > Check now should offer "Beta 2 (test)": Update now downloads, checks and installs it and
     restarts the Launcher, which then says Beta 2. "Back to Beta 1" then tries undoing it.

Needs: the GitHub CLI signed in (as for Make-MVP06-Test-Release), and Make-MVP06-Test-Release.cmd run once.
#>
param(
    [string]$Downloads = (Join-Path $env:USERPROFILE "Downloads"),
    [string]$RepoName = "MVP06-Plus-test",
    [string]$Version = "Beta 2",
    [string]$Pretend = "Beta 1"
)
$ErrorActionPreference = "Continue"
function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host ""; Write-Host "Stopped: $t" -ForegroundColor Red; throw "stopped" }

try {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Fail "the GitHub CLI isn't installed (https://cli.github.com)" }
    $me = (& gh api user --jq .login 2>$null)
    if (-not $me) { Fail "not signed in to GitHub: run gh auth login" }
    $me = $me.Trim()
    $repo = "$me/$RepoName"
    $tag = "test-" + ($Version -replace '\s', '-').ToLower()

    Step "The test release in $repo"
    $vis = (& gh repo view $repo --json visibility --jq .visibility 2>$null)
    if (-not $vis) { Fail "$repo isn't there: run Make-MVP06-Test-Release.cmd first" }
    if ($vis.Trim() -ne "PRIVATE") { Fail "$repo isn't private: this test only uses a private repository" }
    $draft = (& gh release view $tag --repo $repo --json isDraft --jq .isDraft 2>$null)
    if (-not $draft) { Fail "there's no $tag release in ${repo}: run Make-MVP06-Test-Release.cmd first" }
    if ($draft.Trim() -eq "true") {
        & gh release edit $tag --repo $repo --draft=false | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "couldn't publish $tag in $repo" }
        Write-Host "Published $tag in $repo (still private: only you can see the repository)"
    } else {
        Write-Host "$tag is published in $repo"
    }

    Step "A copy to test in"
    $build = Join-Path $Downloads ("MVP06-Plus-" + ($Version -replace '\s', '-'))
    $launcher = Join-Path $build "MVP06-Plus-Launcher.exe"
    if (-not (Test-Path $launcher)) { Fail "there's no test build in ${build}: run Make-MVP06-Test-Release.cmd first" }
    $test = Join-Path $Downloads "MVP06-Plus-updater-test"
    if (Test-Path $test) { Remove-Item $test -Recurse -Force }
    New-Item -ItemType Directory $test | Out-Null
    Get-ChildItem $build -File | Copy-Item -Destination $test
    Write-Host "Copied the program files to $test (no game files: the Launcher shows its Install tab, that's fine)"

    Step "Opening its Launcher as $Pretend"
    $env:MVP06_UPDATE_REPO = $repo
    $env:MVP06_UPDATE_TOKEN = (& gh auth token).Trim()
    $env:MVP06_TEST_VERSION = $Pretend
    Start-Process -FilePath (Join-Path $test "MVP06-Plus-Launcher.exe") -WorkingDirectory $test
    Write-Host ""
    Write-Host "In the Launcher: Settings > Check now. It should offer $Version (test)." -ForegroundColor Green
    Write-Host "  Update now: downloads, checks and installs it, then restarts saying $Version."
    Write-Host "  Then try ""Back to $Pretend"" (undo): it restarts again, as the files from before."
    Write-Host "  Send Claude a screenshot of anything that goes wrong, and the window's text."
} catch {
    if ("$_" -ne "stopped") { Write-Host "Stopped: $_" -ForegroundColor Red }
}
