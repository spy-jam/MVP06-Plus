<#
MVP06-Plus: a test release, made the way a real one is, in your Downloads folder, all private.

  1. unzips MVP06-Plus-repo.zip into Downloads\MVP06-Plus-test\MVP06-Plus (or reuses it)
  2. copies your Xbox game files into its assets (from your current game folder), for the build
  3. builds MVP06.exe (Visual Studio's x64 tools, LLVM clang, CMake, Ninja)
  4. puts the repository on your GitHub as a PRIVATE repository and runs the "release tools" build there
     (MVP06-Plus-Launcher.exe, gcbridge), then downloads them
  5. packs MVP06-Plus-Beta-1.zip as a release is packed, with Mad Dog's three runtime DLLs from his MVP 06 release zip
  6. makes a DRAFT release on GitHub with it (only you can see a draft)
  7. unzips that zip into Downloads\MVP06-Plus-Beta-1, as a player would, and opens it

Needs: Git and the GitHub CLI (https://cli.github.com), signed in once with "gh auth login"; Visual Studio (or its
Build Tools) with the C++ tools, Windows SDK and the "C++ Clang tools" component (or LLVM on PATH).
Run it with Make-MVP06-Test-Release.cmd (beside it), or:  powershell -ExecutionPolicy Bypass -File Make-MVP06-Test-Release.ps1
Nothing from the game is ever pushed: assets, gc_icons and ps2_icons are in .gitignore, and that's checked.
#>
param(
    [string]$Downloads = (Join-Path $env:USERPROFILE "Downloads"),
    [string]$GameDir = "",          # your current MVP06 folder (with assets\default.xbe); asked for if not given
    [string]$RepoName = "MVP06-Plus",
    [string]$Version = "Beta 1",
    [switch]$SkipBuild,             # use the MVP06.exe already built in the work folder
    [switch]$Final                  # the real release's draft: tag beta-1, no "(test)" (still a draft until you publish)
)
# "Continue": Windows PowerShell 5.1 turns a program's stderr into a stopping error under "Stop" (git and gh write
# progress there), so each step checks its own result, and the file steps below stop on errors by themselves
$ErrorActionPreference = "Continue"
$PSDefaultParameterValues = @{ "*-Item:ErrorAction" = "Stop"; "Expand-Archive:ErrorAction" = "Stop"; "Copy-Item:ErrorAction" = "Stop" }
$env:MVP_NO_PAUSE = "1"
$script:rewritten = $false   # Build-Source.cmd: don't wait for a key at the end
function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host ""; Write-Host "Stopped: $t" -ForegroundColor Red; throw "stopped" }
function Need($cmd, $why) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Fail "$cmd isn't installed ($why)" } }

try {
    $work = Join-Path $Downloads "MVP06-Plus-test"
    $repo = Join-Path $work "MVP06-Plus"
    $tag = ($Version -replace '\s', '-').ToLower()
    if (-not $Final) { $tag = "test-" + $tag }
    $title = "MVP06-Plus $Version" + $(if ($Final) { "" } else { " (test)" })
    $zipName = "MVP06-Plus-" + ($Version -replace '\s', '-') + ".zip"

    Step "Checking what's needed"
    Need git "https://git-scm.com"
    Need gh "the GitHub CLI: https://cli.github.com, then run: gh auth login"
    & gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Signing in to GitHub (once)..."
        & gh auth login --web --git-protocol https
        if ($LASTEXITCODE -ne 0) { Fail "not signed in to GitHub" }
    }
    $me = (& gh api user --jq .login).Trim()
    Write-Host "GitHub account: $me"
    $repoZip = Get-ChildItem $Downloads -Filter "MVP06-Plus-repo*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $beta3 = Get-ChildItem $Downloads -Filter "MVP06*Public*Beta*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $beta3) { Fail "Mad Dog's MVP06_Public-Beta zip isn't in ${Downloads}: it has the three runtime DLLs" }

    Step "Source"
    $mark = Join-Path $repo ".git\mvp-imported-zip.txt"
    if (Test-Path (Join-Path $repo ".git")) {
        Write-Host "Using $repo"
        # a newer MVP06-Plus-repo.zip in Downloads: its new commits brought in (the build is kept)
        $stamp = if ($repoZip) { $repoZip.LastWriteTimeUtc.Ticks.ToString() } else { "" }
        $seen = if (Test-Path $mark) { (Get-Content $mark -Raw).Trim() } else { "" }
        if ($repoZip -and $stamp -ne $seen) {
            $in = Join-Path $work "incoming"
            if (Test-Path $in) { Remove-Item $in -Recurse -Force }
            Expand-Archive $repoZip.FullName -DestinationPath $in -Force
            Push-Location $repo
            try {
                & git fetch -q (Join-Path $in "MVP06-Plus") main
                & git merge -q --ff-only FETCH_HEAD 2>$null
                if ($LASTEXITCODE -ne 0) {
                    # the zip's history was rewritten (as when the commits' email changed): take it as it is. Only
                    # files git keeps are replaced; assets and the build, which it ignores, stay.
                    & git reset -q --hard FETCH_HEAD
                    if ($LASTEXITCODE -ne 0) { Fail "couldn't take the history in $($repoZip.Name)" }
                    $script:rewritten = $true
                    Write-Host "The history in $($repoZip.Name) was rewritten: using it"
                }
                Write-Host "Updated from $($repoZip.Name): $(& git log -1 --format=%s)"
            } finally { Pop-Location }
            Remove-Item $in -Recurse -Force
            Set-Content $mark $stamp
        }
    } else {
        if (-not $repoZip) { Fail "MVP06-Plus-repo.zip isn't in $Downloads" }
        New-Item -ItemType Directory -Force $work | Out-Null
        Write-Host "Unzipping $($repoZip.Name)"
        Expand-Archive $repoZip.FullName -DestinationPath $work -Force
        if (-not (Test-Path (Join-Path $repo ".git"))) { Fail "the zip didn't hold an MVP06-Plus folder with its git history" }
        Set-Content $mark $repoZip.LastWriteTimeUtc.Ticks.ToString()
    }
    Get-ChildItem $repo -Recurse -File | Unblock-File

    Step "Xbox game files for the build"
    $xbe = Join-Path $repo "assets\default.xbe"
    if (-not (Test-Path $xbe)) {
        if (-not $GameDir) {
            Add-Type -AssemblyName System.Windows.Forms
            $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
            $dlg.Description = "Your current MVP06 game folder, or its assets folder (the one with default.xbe)"
            if ($dlg.ShowDialog() -ne "OK") { Fail "no game folder chosen" }
            $GameDir = $dlg.SelectedPath
        }
        # the game folder, its assets folder, or any folder with default.xbe directly in it
        $src = $null
        foreach ($c in @($GameDir, (Join-Path $GameDir "assets"))) {
            if (-not $src -and (Test-Path -LiteralPath (Join-Path $c "default.xbe"))) { $src = $c }
        }
        if (-not $src) { Fail "there's no default.xbe in $GameDir or in an assets folder inside it" }
        Write-Host "Copying $src (a few GB, once)"
        & robocopy $src (Join-Path $repo "assets") /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "copying the game files failed (robocopy $LASTEXITCODE)" }
    } else { Write-Host "Already in assets" }

    Step "Building MVP06.exe"
    $exe = Join-Path $repo "MVP06.exe"
    if ($SkipBuild -and (Test-Path $exe)) {
        Write-Host "Using the MVP06.exe already there"
    } else {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
        if (-not (Test-Path $vswhere)) { Fail "Visual Studio (or its Build Tools) isn't installed" }
        $vs = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)
        if (-not $vs) { Fail "Visual Studio has no C++ tools (add 'Desktop development with C++')" }
        $devcmd = Join-Path $vs "Common7\Tools\VsDevCmd.bat"
        # clang: Visual Studio's own (the "C++ Clang tools" component), LLVM's installer, or already on PATH
        $llvm = $null
        foreach ($c in @((Join-Path $vs "VC\Tools\Llvm\x64\bin"), (Join-Path $env:ProgramFiles "LLVM\bin"),
                         (Join-Path ${env:ProgramFiles(x86)} "LLVM\bin"))) {
            if (-not $llvm -and (Test-Path (Join-Path $c "clang++.exe"))) { $llvm = $c }
        }
        if (-not $llvm) {
            $onpath = Get-Command clang++ -ErrorAction SilentlyContinue
            if ($onpath) { $llvm = Split-Path $onpath.Source }
        }
        if (-not $llvm) {
            Fail ("clang isn't installed. In Visual Studio Installer: Modify > Individual components > tick " +
                  "'C++ Clang Compiler for Windows' and 'C++ CMake tools for Windows', Modify, then run this again " +
                  "(or install LLVM from https://github.com/llvm/llvm-project/releases)")
        }
        Write-Host "clang: $llvm"
        $path = "set `"PATH=$llvm;%PATH%`" && "
        if (Test-Path $exe) { Remove-Item $exe }
        & cmd /c "call `"$devcmd`" -arch=x64 -host_arch=x64 >nul && $path cd /d `"$repo`" && Build-Source.cmd"
        if (-not (Test-Path $exe)) {
            Fail "the build didn't make MVP06.exe (see above; clang needs Visual Studio's 'C++ Clang tools' component or LLVM)"
        }
    }

    Step "Your private GitHub repository"
    Push-Location $repo
    try {
        $tracked = & git ls-files
        $bad = $tracked | Where-Object { $_ -match '^(assets/(?!PUT-GAME-FILES-HERE)|gc_icons/|ps2_icons/)' -or $_ -match '\.(xbe|big|iso)$' }
        if ($bad) { Fail "game files would be pushed: $($bad | Select-Object -First 3)" }
        & gh repo view "$me/$RepoName" *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Making $me/$RepoName (private)"
            & gh repo create $RepoName --private --source . --remote origin --push
            if ($LASTEXITCODE -ne 0) { Fail "couldn't make the repository" }
        } else {
            $vis = (& gh repo view "$me/$RepoName" --json visibility --jq .visibility).Trim()
            Write-Host "$me/$RepoName is there ($vis)"
            if (-not (& git remote)) { & git remote add origin "https://github.com/$me/$RepoName.git" }
            & git push -u origin main 2>$null
            if ($LASTEXITCODE -ne 0) {
                # GitHub's main isn't behind this one: look at what it has. If every change on it is already here
                # (its commits were only rewritten, as when signatures or the email changed), replace it; if it has
                # changes of its own (an edit made on the website, say), stop and name them.
                & git fetch -q origin main
                if ($LASTEXITCODE -ne 0) { Fail "couldn't read the GitHub repository" }
                $theirs = (& git rev-parse FETCH_HEAD).Trim()
                $own = @(& git cherry HEAD $theirs | Where-Object { $_ -like "+*" })
                if ($own.Count -gt 0) {
                    Write-Host "GitHub has changes that aren't in this folder:"
                    foreach ($c in $own) { Write-Host ("  " + (& git log -1 --format="%h %s (%ad)" --date=short $c.Substring(2))) }
                    Fail "bring those into the repo zip first (send the list to Claude), so they aren't lost"
                }
                Write-Host "Replacing the history on GitHub with the rewritten one (no changes of its own are lost)"
                & git push -u "--force-with-lease=main:$theirs" origin main
                if ($LASTEXITCODE -ne 0) { Fail "couldn't push the rewritten history" }
            }
        }

        Step "Building the Launcher and gcbridge on GitHub"
        $before = (& gh run list --workflow release-tools.yml --limit 1 --json databaseId --jq ".[0].databaseId" 2>$null)
        & gh workflow run release-tools.yml --ref main
        if ($LASTEXITCODE -ne 0) { Fail "couldn't start the build (Actions may need turning on in the repository's Actions tab)" }
        $run = $null
        for ($i = 0; $i -lt 30 -and -not $run; $i++) {
            Start-Sleep 3
            $id = (& gh run list --workflow release-tools.yml --limit 1 --json databaseId --jq ".[0].databaseId")
            if ($id -and $id -ne $before) { $run = $id.Trim() }
        }
        if (-not $run) { Fail "the build didn't show up on GitHub" }
        Write-Host "Waiting for it (about 5 minutes)..."
        & gh run watch $run --exit-status
        if ($LASTEXITCODE -ne 0) { Fail "the GitHub build failed: gh run view $run --log-failed" }
        $art = Join-Path $work "artifacts"
        if (Test-Path $art) { Remove-Item $art -Recurse -Force }
        & gh run download $run --dir $art
        if ($LASTEXITCODE -ne 0) { Fail "couldn't download the build's files" }
    } finally { Pop-Location }

    Step "Packing $zipName"
    $stage = Join-Path $work "release-files"
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory $stage | Out-Null
    Copy-Item $exe $stage
    $d3d = Join-Path $repo "d3dcompiler_ms.dll"
    if (Test-Path $d3d) { Copy-Item $d3d $stage } else { Fail "d3dcompiler_ms.dll wasn't made by the build" }
    $b3 = Join-Path $work "beta3"
    if (-not (Test-Path $b3)) { Expand-Archive $beta3.FullName -DestinationPath $b3 -Force }
    foreach ($dll in "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll") {
        $f = Get-ChildItem $b3 -Recurse -File -Filter $dll | Select-Object -First 1
        if (-not $f) { Fail "$dll isn't in $($beta3.Name)" }
        Copy-Item $f.FullName $stage
    }
    foreach ($n in "MVP06-Plus-Launcher.exe", "gcbridge") {
        $f = Get-ChildItem $art -Recurse -File -Filter $n | Select-Object -First 1  # (each artifact comes in a folder of its own name)
        if (-not $f) { Fail "$n isn't in the GitHub build's files" }
        Copy-Item $f.FullName $stage
    }
    $zip = Join-Path $work $zipName
    if (Test-Path $zip) { Remove-Item $zip }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if ($py -and $py.Source -notmatch "WindowsApps") {
        Push-Location $work
        try { & $py.Source (Join-Path $repo "tools\make_release.py") $stage $Version } finally { Pop-Location }
    }
    if (-not (Test-Path $zip)) {
        # no Python: the same files and manifest (gcbridge's executable mark is set by its Steam launch option anyway)
        $pack = Join-Path $work "pack"
        if (Test-Path $pack) { Remove-Item $pack -Recurse -Force }
        New-Item -ItemType Directory $pack, (Join-Path $pack "assets") | Out-Null
        Copy-Item "$stage\*" $pack
        foreach ($n in "README.md", "RELEASE-NOTES.md", "START-HERE.txt", "mvp06-settings.toml", "SDK-LICENSE.txt",
                       "THIRD_PARTY.txt", "MICROSOFT-RUNTIME-NOTICE.txt") {
            if (Test-Path (Join-Path $repo $n)) { Copy-Item (Join-Path $repo $n) $pack }
        }
        Copy-Item (Join-Path $repo "assets\PUT-GAME-FILES-HERE.txt") (Join-Path $pack "assets")
        $m = [ordered]@{}
        Get-ChildItem $pack -Recurse -File | Sort-Object FullName | ForEach-Object {
            $m[$_.FullName.Substring($pack.Length + 1).Replace('\', '/')] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        }
        [IO.File]::WriteAllText((Join-Path $pack "SHA256-MANIFEST.json"), ($m | ConvertTo-Json) + "`n")
        # entries named with / (Compress-Archive in Windows PowerShell writes \, which SteamOS's unzip keeps in names)
        Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
        $za = [IO.Compression.ZipFile]::Open($zip, "Create")
        try {
            Get-ChildItem $pack -Recurse -File | ForEach-Object {
                $name = $_.FullName.Substring($pack.Length + 1).Replace('\', '/')
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($za, $_.FullName, $name, "Optimal") | Out-Null
            }
        } finally { $za.Dispose() }
        Remove-Item $pack -Recurse -Force
    }
    Write-Host "Made $zip"

    Step "Draft release on GitHub (only you can see it)"
    Push-Location $repo
    try {
        & gh release view $tag *> $null
        if ($LASTEXITCODE -eq 0) { & gh release delete $tag --yes | Out-Null }
        & gh release create $tag $zip --draft --prerelease --target main --title $title --notes-file RELEASE-NOTES.md
        if ($LASTEXITCODE -ne 0) { Fail "couldn't make the draft release" }
    } finally { Pop-Location }

    Step "Unzipping it as a player would"
    $player = Join-Path $Downloads ("MVP06-Plus-" + ($Version -replace '\s', '-'))
    if (Test-Path $player) {
        $player = $player + "-" + (Get-Date -Format "yyyyMMdd-HHmm")
    }
    Expand-Archive $zip -DestinationPath $player
    Write-Host ""
    Write-Host "Done." -ForegroundColor Green
    Write-Host "  Player's folder: $player   (run MVP06-Plus-Launcher.exe there, then MVP06.exe)"
    Write-Host "  Draft release:   https://github.com/$me/$RepoName/releases"
    Write-Host "  The repository is private; publishing the draft or making the repository public is up to you."
    Start-Process explorer.exe $player
} catch {
    if ($_.Exception.Message -ne "stopped") { Write-Host ""; Write-Host "Stopped: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
