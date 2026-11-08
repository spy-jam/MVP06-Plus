# MVP 06 NCAA Baseball recomp: PlayStation (and experimental GameCube) controls, handoff

This is for starting a new chat. Attach this file, the latest package (`mvp06-controls-v17.zip`), and `MVP05-HANDOFF.md` with the latest MVP 05 package, which is the reference implementation. Research details and addresses are in `MVP06-NOTES.md` (in this package).

## 1. What this is

- **The base:** Mad Dog's static recompilation of the **Xbox** MVP 06 NCAA Baseball (`default.xbe`, title 4541008D, Source-Build Beta 1). It uses the same recomp SDK (0.1.0) as his MVP 05.
- **What the mod adds, as for MVP 05:**
  - **PlayStation pads** (DualShock 3/4, DualSense, PS3-type PS2 adapters) control and look like the **PS2 release** (`SLUS_213.67`): its action table, stick curve, pressure, and its rumble on the DualShock's two motors. This is the main goal.
  - **GameCube controllers** on the USB adapter, with an **EXPERIMENTAL GameCube layout.** MVP 06 had no GameCube release. The table is MVP 2005's GameCube table carried over, with proposals for the new 06 actions. **Experimental GameCube art** since v2 (`gc_icons`, built by `tools/gc_layout/make_gc_icons06.py`). No GameCube-only screen fixes yet.
  - **Save backups at launch**, and **keep-awake** while a controller is used (the same code as MVP 05 v35/v36).
- **Versioning:** this project has its own numbers, starting at **v1**. The MVP 05 line is separate (v36 at the time of writing).
- Mad Dog has given permission for a fork. Disc-derived files (`ps2_icons`) must never go in a repo; users build them with the tools.

## 2. Build and install

1. Extract the zip over Mad Dog's MVP 06 Source-Build folder (or apply `mvp06-controls.patch` to it: `git apply mvp06-controls.patch`).
2. In the x64 Native Tools prompt: `set PATH=C:\Program Files\LLVM\bin;%PATH%`, then `Build-Source.cmd`.
3. Put `ps2_icons` and `gc_icons` beside `MVP06.exe`.
4. **Settings** (`mvp06-settings.toml`): `playstation_layout`, `playstation_icons`, `gamecube_layout`, `gamecube_icons` (all true) and `save_backups` (10; 0 turns backups off).
5. **To build the art from your own discs:**
   ```
   python tools/ps2_layout/make_ps2_icons06.py <Xbox data folder> <PS2 DATA folder> ps2_icons
   ```
   Needs Pillow and numpy. To gather just the needed files from both discs, use `tools/collect_mvp06.py`.
   ```
   python tools/gc_layout/make_gc_icons06.py <Xbox data folder> <MVP 2005 gc_icons folder> gc_icons
   ```
   The second folder is the `gc_icons` that MVP 2005's `make_icons.py` built (beside `MVP05.exe`). Needs Pillow, numpy, scipy and OpenCV (`pip install pillow numpy scipy opencv-python`).

## 3. Files

| File | What |
|---|---|
| `src/game/gc_controls.cpp/.h` | The 06 port: table swap, PS2 button handling, stick curves, PS2 rumble, art choice |
| `src/game/ps2_layout_table.h` | The PS2 table, from `SLUS_213.67` (`tools/ps2_layout/ps2_extract.py` + `gen_ps2_table.py ... mvp06`) |
| `src/game/gc_layout_table.h` | The EXPERIMENTAL GameCube table (`tools/gc_layout/draft_gc06.py` + `gen_table06.py`) |
| `src/common/game_info.cpp` | Mad Dog's, plus our settings and hooks (`init`, `window`, `pad`, `rumble`) |
| `src/common/save_backup.cpp/.h` | Save backups (as in MVP 05) |
| `sdk/runtime/core/input.cpp/.h`, `gc_adapter.cpp/.h` | Controllers (as in MVP 05). `gc_adapter.cpp` now builds as stubs off Windows, for the SDK's Linux harness |
| `sdk/runtime/kernel/files.cpp`, `kernel.h` | Art overlay folders. Merged with Mad Dog's 06 trace logging |
| `src/game/hooks.cpp` | Mad Dog's, unchanged. None of his hooks overlap ours |
| `sdk/runtime/gpu/d3d12.cpp`, `Build-Source.cmd` | Mad Dog's, plus the Proton shader fix (v3) |

## 4. How the 06 port works (details and evidence in `MVP06-NOTES.md`)

- **Pad and table:**
  - Xbox pad vtable `0x64C518`; table at `+4`, `0x111` entries; controller port at `+0x14DC`.
  - Pad list at `[0x6D5A04] + 0xC + 4*i` (6 slots).
- **Hooks:**
  - `sub_00318190`: the Xbox layout; we save the table, then swap in the port's table.
  - `sub_00317B60`: the pad read; re-sync when a controller changes.
  - `sub_0028E870` / `sub_0028E8E0`: the rumble wrappers.
- **Stick mode flag** `0x6ABA18`; dead-zone table `0x6B0B04`. Both curves and the dead zones are the same as MVP 05, so `XboxStickFor`, `PlayStationStick`, the pressure `t + p/k` and L2/R2 are unchanged.
- **Rumble (new for 06):**
  - The Xbox mixes channels A and B into one level for both motors. The PS2 runs the big motor at a strength and the small one on/off.
  - For a PlayStation player, each Xbox request is mapped by its return address to the PS2's event: motor, strength and frames (the table in `gc_controls.cpp`).
  - Big-motor events go to channel B and small-motor events to channel A. `gc::Rumble` reads the two channels back (`+0x1554` for the big motor, `+0x154C` ≥ 0.5 for the small one) when the game sends its level.
  - New in 06, small motor: the batter's right stick held up (both motors), and the co-op runner cue.
- **Art:** `make_ps2_icons06.py`.
  - Help icons, pitch select (including the 06-only `bu10`–`bu21`), replay, the co-op overlay (`coopov.big`) and the base-runner diamonds.
  - All six layout archives go through `as_platform(..., strict=True)`, which adopts a PS2 group only when it has every group the Xbox one has: 64 adoptions.
  - Left alone: DNAS online login, player cards, and two fielding-HUD copies whose PS2 group lacks `METER`.
  - In 06 the PS2 Select Controller has the same six rows as the Xbox, so it's adopted directly. No `pad_boxes` needed.

## 5. Status

- **v1:** built here only as far as syntax checks against the 06 SDK. **Not compiled on Windows, not run.** The patch applies to a fresh copy of Mad Dog's source.
- **v2:** experimental GameCube art (`gc_icons` + `make_gc_icons06.py`). No code change from v1: no rebuild needed, just add the folder. Steal crash check (MVP 2005 §4.6) done: not expected in 06 (see `MVP06-NOTES.md`).
- **v3:**
  - SteamOS / Proton black screen fix, the same as MVP 2005 v38 (`d3d12.cpp`: Microsoft's compiler beside the exe as `d3dcompiler_ms.dll`, copied by `Build-Source.cmd`, then the `1.#INF` retry). Needs a rebuild.
  - PS2 labels: an icon only the Xbox draws, with the PS2's own icon at the same spot, now draws the PS2's (`icon_twin` in `make_icons.as_platform`, strict mode). Fixes pause Show Info and the ballpark editor's Reset (Circle, not Triangle), plus the in-game option, roster and tuning menus, the controller pages and the keyboards. Only pictures the Xbox data has are used (`picture_names`), so the HUD's PS2-only `l1_n`/`r1_n` stay Xbox unless the full data has them. GameCube: the cutoff prompt shows R.
- **v4:** GameCube 06 fixes from the first test (needs a rebuild for the table and the adapter log; new `gc_icons`):
  - Bunt is Z + A again (`0x0BA`, `0x0BF`: 05's GameCube bunt `0x0B9` is Z hold + A hold; the draft had read it as Z alone).
  - Nav bars kept as the Xbox's, not adopted: 06's GameCube nav groups are 2005's and showed nothing in menus and "A WWWW" placeholders in game. Their icon lists are reordered for the GameCube menus (back B, Random Y, profile X). GameCube adoption is also stricter (`strict='leaves'`).
  - The help sheet holds each GameCube button in the slot of the Xbox button whose jobs it does (bu01 X, bu02 B, bu03 Y); what 2005's GameCube groups draw is renamed to match (`GC_SWAP`).
  - Base runner diamond: 06 picks each base's picture by the bound button's channel (PXB + letter), so each picture now shows its own letter. It read Y third, X second, B first; it now reads B third, Y second, X first, as 2005's GameCube.
  - Pitch select: the GameCube buttons on the Xbox's own spots (36/32 px), so they no longer cover the pitch names.
  - Pads 42 px wide (four sit side by side on team select); the outline and silhouette taller and smoother.
  - The adapter logs what it saw when it finds nothing (see MVP 2005 v39, for Proton).
- **v5:** GameCube adapter under Proton. Wine's HID layer finds the adapter but refuses its 1-byte start report (error 87), so `gc_adapter.cpp` now opens the adapter's Linux hidraw node itself through Wine's Z: drive (`OpenLinuxHidraw`: found by `HID_ID=0003:0000057E:00000337` under `/sys/class/hidraw`), as Dolphin talks to it. Needs Steam's own GameCube support off; `PROTON_ENABLE_HIDRAW` isn't needed. On Windows nothing changes.
- **v6:** the hidraw start report is sent as 2 bytes (`13 00`): Linux's hidraw refuses writes under 2 bytes with EINVAL, which Wine reported as error 87.
- **v7:** diagnostics: the adapter's first 6 reads (and up to 20 odd-sized ones) go in the log as hex. On Proton (v41) it opened and took the start report but no controller ever showed up.
- **v8:** GameCube adapter under Proton through a Linux helper, `gcbridge` (source `tools/gcbridge/gcbridge.c`, a static Linux build beside the exe). v42 showed the hidraw route opens but never gets a report: Linux's hidraw can't send the adapter's 1-byte start report (2 bytes minimum), and the adapter ignores `13 00`. `gcbridge` talks to the adapter over usbfs as Dolphin does (detaches the kernel HID driver, claims interface 0, sends `13` on EP 02) and passes each 37-byte report to the game over UDP on 127.0.0.1:47337 (rumble back the same way). The game starts it by itself under Wine (`OpenBridge`, tried before hidraw); it quits 5 s after the game stops. It must be executable (`chmod +x gcbridge`). Build: `cc -O2 -static -s -o gcbridge gcbridge.c`.
- **v9:** `gcbridge` writes `gcbridge.log` beside the exe (USB devices seen, open/claim/start errors, the game's hello, the first report). With `gcbridge` present the game no longer falls back to hidraw (whose read never returns).
- **v10:** GameCube adapter under Proton, both routes reworked. **hidraw is first again, with the start report fixed:** a hidraw write starting `00` is a report without an id, and the kernel (`usbhid_output_report`) drops the `00` and sends the rest, so `00 13` reaches the adapter as the single `13` Dolphin sends (`13 00`, sent before, went as two bytes and the adapter ignored it; every earlier hidraw log opened and then logged no read at all). The hidraw node is read on its own thread with its own handle, so a silent adapter can't hang the loop: no report within 2 s (start sent twice) and it moves on to `gcbridge` for the session. **gcbridge:** it binds its port before opening its log, so a second copy exits without overwriting the first's log. It sends its log lines to the game (`GCL1` + text, put in the game's log as `gcbridge: ...`, with lines from before the game's hello buffered) and a heartbeat every second (`GCA1`). The game doesn't relaunch it while it's heard from, and deletes the old `gcbridge.log` before a launch. If the game hears nothing, it copies `gcbridge.log` into its own log, or says Wine never ran it and suggests the launch option `./gcbridge & %command%`. The bridge uses `USBDEVFS_DISCONNECT_CLAIM`, with the older disconnect and claim as fallback. Its log lines name the interface's current driver; on a failed open, the node's mode, owner and group against its own uid and groups (or that the node is missing in Steam's container); and on a failed claim, the processes holding the node. If no report arrives it resends the start (at 1, 2, ... s, five times), clears an IN stall, and gives the kernel driver back if the start fails.
- **v11:** v45's test: hidraw took `00 13` but sent nothing, and Wine said gcbridge "started" but it left no log and never answered. Wine starts a Linux program with fork and exec and calls it success once the exec is under way (Wine's `fork_and_exec`; no handles come back), so "started" proved nothing. Now: (1) the game starts gcbridge through `Z:\bin\sh -c '...' <unix path>` (path from `wine_get_unix_file_name`, else Z: stripped). The shell marks it executable when it isn't (no chmod by hand) and writes `gcbridge.out` beside it: that it ran, `ls -l`, the program's own lines (it copies each to stderr) and its exit code. If the game hears nothing in 4 s, `gcbridge.out` and `gcbridge.log` are copied into its log; if neither exists, nothing ran at all. Tested here with the exact command line split by Windows' rules, on a non-executable file in a folder with a space. (2) The game checks that the `gcbridge` beside the exe holds `GCBRIDGE-PROTOCOL-3` and says when it's an older one. (3) The bridge is tried before hidraw: SDL (it marks 057e:0337 as libusb-only) and Dolphin both drive this adapter only through libusb, never hidraw. hidraw is kept as a last resort and now logs what it reads. (4) The bridge finds its interrupt endpoints in sysfs (`ep_*/type`, `direction`), is built `-march=x86-64` (baseline ISA), waits 180 s for the first hello (so it can be started from Steam's launch options before Proton), and falls back to `/tmp/gcbridge.log`. Tested against a fake adapter (an LD_PRELOAD shim over sysfs, usbfs and ioctl): disconnect and claim, control 21/11/1, the 1-byte `13`, about 125 reports a second to the game, rumble out, the start resent when the first is ignored, and the driver given back at exit. Fallback that bypasses Wine and Steam's container: launch options `sh -c 'B="<full path>/gcbridge"; chmod +x "$B"; "$B" & exec "$@"' sh %command%`.
- **v12:** GameCube art fixes from James's v11 screenshots (no rebuild: just the new `gc_icons`). (1) **The bug behind the pause menu's "A WWWWWWW" bar and the Select Controller mess:** `make_icons.as_platform`, when swapping icon names (`swap`, GameCube only), also set the Xbox flag on every line the GameCube draws. So every GameCube-only group was switched on next to the Xbox one: 159 lines, including `NAVGROUPGC` in every `fes_navbar` (2005's bar: empty texts, every icon A), `GR:GC` / `GG:GCCONTROLLER` on both Select Controller screens and the in-game controller menu, the HUD and bullpen `OTHER` groups, the quick menus, `GCMENU`, `GCNAVBAR`. Now only the names are swapped and the flags are left alone. `scratch`-style check: no GameCube-only group is shown on the Xbox in any archive. MVP 2005's copy is left as it is (its GameCube groups are its own release's, current). (2) **Pads:** `gpco` (drawn under each pad on Select Controller) and `gpdx` (the CPU outline) are now the GameCube pad's own shape grown 3 px, as the Xbox's are its pad's bounds plus 3, so only a white rim shows round a pad. Before, a stretched pad stuck out as a grey blob, and the outline read as an Xbox pad. Light smoothing keeps the dip between the handles. (3) **Fifth pitch:** R tucked right under the tile (its picture's empty margin cropped), as PS2 06 puts R1 and 2005 its R. Pause Show Info shows Y, correct (the Xbox uses bu03 = Y there).
- **v13:** From James's v12 test (**needs a rebuild** for the table; new `gc_icons`). (1) **Hit the batter (Z + D-Down) didn't work:** 06 reads a separate "White held" action (0x0DC) as the modifier for its four D-pad pitch options (05 had three, and no such read). The table had copied 05's match for it (05 0x0D5), which 05's GameCube left unbound. It's now Z hold (`DECIDED` in `draft_gc06.py`, which now goes first so a decision can override a 05 match). Nothing else in the table changed. (2) **Show Info showed Y; it's X:** in the menus, action 0x004 (the Xbox's Y) is GameCube X and 0x003 (the Xbox's X) is GameCube Y, as in 2005; the nav bars already account for this (`NAV_LIST`). The DETAILS button in the pause, option, roster, online option and tuning menus (Show Info and its counterparts) now takes the same remap (`details_x`: bu03 -> bu01, the X picture). The controller info pages, keyboards and meters keep the help sheet's in-game slots (unreported; check if they look wrong). (3) **START too close to its label:** bq00/bq01 (2005's START, the word over a dot) filled the whole 32 px; now fitted to x 5-26 like every Xbox button, where the label starts just past it.
- **v14:** From James's v13 test (**needs a rebuild** for the table; new `gc_icons`). (1) **Wall editor:** Reset showed Y but is X (the Xbox's Y there, like Show Info): `details_x` also covers `fes_ballpark_hud`'s BOTTOM groups, and any Xbox-drawn icon in its groups. Hide (the Xbox's L3, drawn as Z) did nothing: 06's LS click press 0x04E had 05's match (05 0x04C), unbound on 05's GameCube, which had no editor. It's now Z press (`DECIDED`). (2) **Show Info's X looked odd:** 2005's X picture is 30 px tall; bu01 (X) and bu03 (Y) are now fitted to 25 px. (3) **START too small after v13:** it now ends at x 26 (where the label starts) but may use the free space to its left, up to 27 x 26. (4) **Pitch cross:** GameCube Y 3 px higher (`NUDGE`); GameCube X (on the Xbox B spot) 29 px instead of 32 and 2 px toward the hub (sheet pixels, scaled per sheet).
- **v15:** From James's v14 test: hit the batter and the editor's Hide still didn't work (**needs a rebuild**, table only; `gc_icons` as v14). (1) **Hit the batter (Z + D-Down):** 0x077, the White-held modifier of the White + D-pad pitch commands (0x077-0x082), had 05 GC's "while Z: source 189". 189 is the only source in the table that 06's Xbox table never uses (06 uses 181, 183-188, 191), so in the 06 build it likely reads nothing and the modifier never holds. It's now plain Z hold, the Xbox entry with White moved, exactly as PS2 06 binds it (R2 hold). v13's 0x0DC (Z hold) stays: the Xbox binds White hold there. (2) **Editor Hide (the Xbox's L3):** 06's menu screens read L3 through the generic button events 0x018 (repeat) and 0x019 (release), which 05 GC, without an L3, left empty. Both are now Z. v14's 0x04E (an in-game action) is back to 05's unbound. If either still fails, the next step is logging which actions turn on while a button is held, rather than another guess.
- **v16:** **Hit the batter (GameCube L + D-Down; Xbox LT + L3), traced in the 06 executable** (**needs a rebuild**, table only). The pitching input chain (`0x2A8AE4`) runs `0x2A01E0` every frame unless the state is 0, 1 or 3. That handler asks `0x28FAA0` (value != 0, via `0x28F6C0`: context mask `0x6AB188[action] & 0x6AB174`, then the pad evaluator `0x28ECC0` -> alias lookup vtable `+0x60` = `0x317AD0` -> combine `0x28DCF0`, ops: 0 or, 1 and, 2 a-and-not-b, 3 minus, 4/5 while/unless) for **0x0AD**; if true (and the game's conditions hold) `0x1F1410` sets state 4, hit the batter. Else it asks **0x074** (LT held) and, unless the state is 1 or 3, `0x1F1440` sets state 2, pickoff. The Xbox binds 0x0AD as LT hold + L3 hold (true every frame while held) and 0x074 as LT hold without L3 hold, so the two never compete. 05 GC's binding (0x0AD L hold + D-Down **press**, 0x074 plain L hold) made hit-batter true for one frame, and the next frame 0x074 (L still held) turned it into pickoff. Now 0x0AD = L hold + D-Down hold and 0x074 = L hold without D-Down hold, the Xbox's form with D-Down in L3's place; it works with L first, Down first or both together. The guesses from v13 and v15 (0x0DC Z hold, 0x077 Z hold) are back to 05's. 0x0D3-0x0D6 (the D-pad holds) are read only by the baserunner code (`0x2174B8`), so holding Down while pitching triggers nothing else. **Editor Hide** stays as v15 (0x018/0x019, the menus' L3 events, on Z); it hasn't been traced in the code (`0x11C0E0` raises a 0x18/0x19 event; `0x120600` reads 0x076 for the game's controller -> `0x644D0`).
- **v17:** Last build before a long test (**needs a rebuild**). (1) **Shader cache** (`d3d12.cpp`, the SDK's renderer, the same code in 05 and 06): each compiled shader is saved in `shader_cache` beside the exe (`<key>.bin`: a 32-byte header with magic `MVCS`, version 1, the key, a hash of the bytes and their size, then the compiled shader) and loaded on later runs, instead of compiled the first time it's drawn every run (a hitch, slower under Proton). The key is the in-memory cache's hash (source, entry point, profile) salted with the format version and which compiler (`d3dcompiler_ms.dll` or the system's). A file that's missing, truncated, for another key or fails its hash is ignored and compiled and rewritten. Written to `.tmp` and renamed. The log says once that it's loading from the cache. Delete the folder to clear it. Tested here against stand-ins (save, reload, another compiler, a corrupted file, a truncated file, rewrite). (2) **Adapter under Proton, quieter:** the game stops starting gcbridge itself after 3 starts it never heard from (it still listens every second, for one started from Steam's launch options), and "adapter found (HID) but would not start", Wine's HID route refusing the start report every few seconds, is said 3 times, not all session. **Proton setup (works, James 2026-11-03):** Steam's GameCube support off, and in the game's Steam launch options `sh -c 'B="<game folder>/gcbridge"; chmod +x "$B"; "$B" & exec "$@"' sh %command%`. The game's own start of gcbridge under Wine never ran (Wine reports success at the exec; the cause wasn't found), so the launch option is the way. 06 GameCube status: Z (editor Hide, v15) confirmed working by James. **Hit the batter (L + D-Down) still does not work, v16 included** (James, 2026-11-05): v16's `0x2A01E0` analysis is a lead, not the whole cause. Next: log which actions turn on while L and Down are held, rather than another change by reasoning.
- **To test first:**
  - The game starts and the log shows `gc: port N now has the PS2 layout`.
  - Triangle backs out of menus.
  - Pitch select shows the PS2 diamonds.
  - Rumble: the pitch cursor and fielding events, plus the new small-motor buzzes.
  - Pressure on a DualShock 3.
  - Save backups appear in `save backups`.
- **Experimental GameCube:** watch Z, which carries Back, the modifier and the new 06 actions (and shows for L3/R3 in the art). Check the GameCube art: help bar, pitch select (buttons, the fifth pitch tile top right with R, the stick/D-pad pictures), Select Controller pads, replay panel, co-op pitch select.
- **Steal a base** once (the crash MVP 2005 needed a config fix for). If it ever crashes, the log's `indirect call to XXXXXXXX` address goes in `config/game.toml [functions]`.
- **Unknowns:**
  - The two animation states in the batter right-stick event are hashes.
  - Whether 05's PS2 also used the small motor (could be checked against `SLUS_211.35`).

## 6. Next steps

- Test v1 and fix what shows up.
- The GameCube-only screen fixes (title screen, replay Y, attract demo) need their 06 addresses.
- The fork and installer plan from `MVP05-HANDOFF.md` §6.4 applies to both games.

## 7. GameCube 06 art (v2, experimental)

`tools/gc_layout/make_gc_icons06.py` (docstring has every detail). Sources: the Xbox 06 data and MVP 2005's built
`gc_icons` (its GameCube pictures, pitch art, replay panel, base diamonds and loading screen 3). Design approved by
James on 2026-10-31:
- **Pitch select, option A:** the Xbox 06 cross; GameCube buttons in 2005's GameCube arrangement at 90% of its
  spacing (offsets from the hub centre A (0.5,21), Xbox-B slot (26.5,1.5), Xbox-X slot (-23,0), Y (1,-25), scaled by
  each sheet's own button spacing), 2005 sizes (A 38 px canvas, others 34), A drawn last. The Xbox B slot shows
  GameCube X and the X slot shows B (2005's swap). Old Xbox buttons erased by `refill` (bars refilled from their own
  part of the cross, the hub with each row's flat colour). The co-op sheet (`coopov.big`, older 155x129 pictures) the
  same way at its own scale.
- **Fifth pitch:** the Xbox black-button tile moved to the top right (flipped, as PS2 06 draws it) with GameCube R
  under it.
- **Sticks and D-pad** (bq08/bq09, bu10-bu21) drawn after 2005's GameCube loading screens: indigo disc, octagonal
  cap (grey with ridges / yellow with a raised C), cream arrows; the D-pad's pressed arm yellow (06's convention).
- **Pads** (gpad, gpa2 at 48%) from the controller cut out of 2005's loading screen 3 (OpenCV grabCut, seeded by its
  indigo), 42 px wide; gpdx (CPU outline) and gpco (silhouette under a pad) the pad's own shape grown 3 px (v12).
- **Help buttons:** 2005's GameCube pictures; bq00 START fitted to 32x32; L3/R3 (bu08/bu09) a drawn purple Z;
  mi02/mi10 a drawn flash.
- **Layouts:** strict GameCube adoption on all six archives; online and voice chat labels keep the Xbox flags
  (`keep_online`; the PS2 build still hides Xbox Live labels the PS2 group doesn't show; worth the same guard).
  Left as Xbox where the GameCube group is stale: Select Controller (both), the in-game controller menu.

## 8. The steal crash check (how, for any future game)

MVP 2005 crashed stealing a base because a handler stored into a table at run time wasn't recompiled. For 06:
1. Build `xbe_recomp` alone on Linux (Zydis + toml++ from `vendor/`) and run it on the XBE:
   `xbe_recomp config/game.toml default.xbe <out> --xdk sdk/xdk` (8 s). `<out>/x86_func_mapping.cpp` lists every
   recompiled function.
2. Scan the disassembly for code addresses the program stores or pushes (`mov [mem], imm`, `push imm`, any
   immediate) and for code addresses in the data sections; keep those that look like function starts (an
   instruction start after padding or a ret) and aren't in the list.
3. Result for 06: none (all 81 raw hits are numbers or text). The run-time handler tables (the 36 stores of
   `0x147580`, 06's version of 2005's `0x42B950`, and three more) all point at recompiled functions.

## Release work (MVP06-Plus Beta 1)

Built the same way as MVP05-Plus (see its handoff's "Release work"): Mad Dog's MVP06 Public Beta 1 source, the v17 controller patch, then the fork's game changes from 05 (Esc asks to quit, `app::AppIcon` / the icon from the disc, the missing-game message pointing at the Launcher, 30 save backups, fullscreen at the desktop's resolution).

- **Launcher** (`tools/installer`, the 05 Launcher with 06's details):
  - Xbox title `4541008D` (`discs.XBOX_TITLE`), PS2 serial `SLUS_213.67`; saves in `hdd/E/UDATA/4541008d`.
  - PS2 art from the 06 PS2 disc: only `DATA/FRONTEND/SHARED.BIG`, `IGONLY.BIG`, `COOPOV.BIG` and `DATA/IGSHAPES/IGCRSR.SSH` are read (`discs.PS2_ART_FILES`), into `make_ps2_icons06.py` (the layouts come from the Xbox game's own files).
  - GameCube art (behind the *Experimental GameCube support* box): there was no GameCube MVP 06, so it's made from MVP 2005's GameCube art, run through `make_gc_icons06.py` (needs scipy and OpenCV, bundled in the exe). That 2005 art comes from either the MVP 2005 GameCube disc together with the MVP 2005 Xbox disc (`install.build_gc_from_discs`: only `discs.GC05_ART_FILES`, 11 files, and `discs.XBOX05_ART_FILES`, 14, are read, then `tools/gc_layout/make_icons05.py`, MVP05-Plus's own copy, makes 2005's set in a temporary folder), or an MVP05-Plus folder or its `gc_icons` (recognised by `load3.big`). A 06 `gc_icons` set is copied as it is.
  - Checked against the v17 package: with the real 06 Xbox files, the 06 PS2 files and 05's gc_icons, both sets come out byte for byte the same.
- **Release scripts:** `tools/Make-MVP06-Test-Release.cmd` / `Make-MVP06-Final-Release.cmd` take Mad Dog's `MVP06_Public-Beta` zip from Downloads for the runtime DLLs.
