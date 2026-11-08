# Making a release

1. **Push this repository to GitHub** (once): create an empty repository named `MVP06-Plus` on github.com (no README), then in this folder:
   ```
   git remote add origin https://github.com/<you>/MVP06-Plus.git
   git push -u origin main
   ```
   If you'd rather show it as a fork of Mad Dog's repository, fork his on GitHub first and push to your fork instead.
2. **Build the release tools:** on GitHub, open *Actions → release tools → Run workflow*. When it finishes, download its two artifacts, `MVP06-Plus-Launcher` and `gcbridge`, and unzip them.
3. **Build the game** on your PC as the README says (`Build-Source.cmd`), and copy Mad Dog's three VC runtime DLLs (`msvcp140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`) from his Public Beta package.
4. **Put the zip together:** gather those files in one folder (`MVP06.exe`, `d3dcompiler_ms.dll`, the three DLLs, `MVP06-Plus-Launcher.exe`, `gcbridge`), then:
   ```
   python tools/make_release.py <that folder> "Beta 1"
   ```
   Check the zip has no `assets` files besides `PUT-GAME-FILES-HERE.txt`, and no `gc_icons` or `ps2_icons`.
5. **Publish:** on GitHub, *Releases → Draft a new release*, tag `beta-1`, title `MVP06-Plus Beta 1`, paste `RELEASE-NOTES.md` as the description, attach `MVP06-Plus-Beta-1.zip`, and tick *Set as a pre-release*.

## A private test release, automatically

`tools/Make-Test-Release.cmd` does steps 1-5 privately in your Downloads folder: it unzips `MVP06-Plus-repo.zip`, copies your Xbox files in from your game folder, builds `MVP06.exe`, pushes to a **private** GitHub repository, runs the release tools build there and downloads it, packs the zip with Mad Dog's DLLs (from his `MVP06_Public-Beta` zip in Downloads), makes a **draft** release, and unzips the zip into `Downloads\MVP06-Plus-Beta-1` as a player would. It needs Git, the GitHub CLI (`gh`, signed in once with `gh auth login`) and Visual Studio's C++ and Clang tools. Run it again after changes: it reuses what's there and replaces the draft.

For the real release, run `tools/Make-Final-Release.cmd` instead: the same steps, but the draft is tagged `beta-1` and titled "MVP06-Plus Beta 1". It stays a draft until you press *Publish release* on GitHub (tick *Set as a pre-release*).
