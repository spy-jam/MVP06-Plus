# MVP06-Plus

MVP 06 NCAA Baseball on Windows, and on SteamOS (Linux) through Proton, built on [Mad Dog's](#credits) PC port of the Original Xbox game. spy_jam's MVP06-Plus keeps Xbox controller support and adds PlayStation controller support with the PS2 release's full control layout and button labels, and experimental GameCube controller support. Includes a launcher for easy installation, dynasty imports from the PS2, save backups, display settings and updates.

> **You need your own copy of the Xbox game.** No game files or game art are included. The Launcher builds what's needed from your own discs.

## Features

* **PlayStation controllers** with the PS2 release's full control layout and stick handling, analog button pressure and rumble.
* **GameCube controllers (experimental)** through a Wii U / Switch adapter: all 4 ports and rumble, with GameCube stick deadzones, C-stick and analog trigger handling. There was no GameCube MVP 06, so the layout follows MVP 2005's GameCube release as closely as 06 allows.
* **Button art to match your controller**: PS2 buttons in menus and in-game, made from your own MVP 06 PS2 disc, and GameCube buttons made from MVP 2005's GameCube art (both optional).
* **Import dynasties** from the PS2 or another Xbox, converted into your MVP06-Plus saves.
* **MVP06-Plus Launcher**: install from your discs, launch the game, import and restore saves, adjust display settings, and update MVP06-Plus.
* **Fixes**: a shader cache to prevent mid-game stutter, and SteamOS support through Proton.
* **Save backups**: a full save backup menu in the Launcher. Your saves are backed up automatically when the game starts, keeping the latest 30 backups by default, and you can view and restore them in the Launcher.

## Compatible controllers

* **DualSense, DualShock 4** — PS2 button art and controls
* **DualShock 3** — PS2 button art and controls, with pressure-sensitive buttons (on Windows, through [DsHidMini](https://github.com/nefarius/DsHidMini) in SDL mode)
* **Xbox 360, Xbox One and Xbox Series controllers** — Xbox button art and controls, as the original
* **GameCube controllers** (official adapter, or a third-party adapter in Wii U mode) — GameCube button art and experimental controls
* **Other controllers** (Switch Pro and most others SDL supports) — Xbox button art and controls

Button art follows the controller connected when the game starts. Without the art sets, PlayStation and GameCube controllers still use their own control layouts, with Xbox buttons shown.

## Coming from Beta 1 or Mad Dog's MVP06

Unzip MVP06-Plus into a new folder and open the Launcher. It asks to bring over your game, saves and settings, so you don't need your discs again. Said no? Press **Ctrl+Shift+B** in the Launcher to be asked again.

## Install

1. Download the latest `MVP06-Plus` zip from [Releases](../../releases) and unzip it anywhere. Everything stays in that folder: nothing goes into Program Files or the registry, and desktop shortcuts are only made if you ask.
2. Run `MVP06-Plus-Launcher.exe` and choose your discs:

   * **Xbox** (required): a Redump `.iso`, `.xiso`, or a folder of extracted files.
   * **PS2** (optional, for PS2 art): your MVP 06 NCAA Baseball PS2 disc, `.iso`, or `.chd` with MAME's `chdman` (the Launcher finds it, or asks where it is). Only the 4 files the art needs are read from it.
   * **Experimental GameCube support** (optional): tick it for GameCube button art. There was no GameCube MVP 06, so the art is made from MVP 2005's: choose your **MVP 2005 GameCube disc** and **MVP 2005 Xbox disc** (only the files the art needs are read from each), or just your **MVP05-Plus folder** if it has GameCube art. It takes a minute or two.
   * Already have an MVP 06 `gc_icons` or `ps2_icons` set? Choose its folder or `.zip` instead.

3. Press **Launch MVP 06**. From then on, the Launcher opens on what's installed, with Launch. To quit the game, press **Esc** (it asks first).

Windows may warn that the Launcher is from an unknown publisher: choose *More info → Run anyway*.

## Setting up controllers

* **GameCube adapter on Windows:** give it the WinUSB driver with [Zadig](https://zadig.akeo.ie/), as for Dolphin (select *WUP-028*, *WinUSB*, *Replace Driver*). Third-party adapters: set the switch to *Wii U*.
* **PlayStation and Xbox controllers:** connect by USB or Bluetooth as usual.

### SteamOS (Proton)

Add `MVP06.exe` to Steam as a non-Steam game, run with Proton. For the GameCube adapter, turn off Steam's own GameCube adapter support and set the launch options (with your folder's path):

```
sh -c 'B="/home/deck/Games/MVP06-Plus/gcbridge"; chmod +x "$B"; "$B" & exec "$@"' sh %command%
```

## Adding to Steam (optional)

1. In Steam: *Games → Add a Non-Steam Game to My Library*, and choose `MVP06.exe`.
2. Playing with a PlayStation or Switch controller? In the game's *Properties → Controller*, choose *Disable Steam Input*. Otherwise Steam passes it to the game as an Xbox controller, with the Xbox layout and buttons.
3. On SteamOS, also follow the Proton steps above.

## MVP06-Plus Launcher

* **Install**, which becomes **Play** once the game's installed: your discs in, then what's installed (checked each start), **Launch MVP 06**, and which controllers Windows sees right now, including whether the GameCube adapter has the WinUSB driver it needs.
* **Saves**: *Your saves*, with *Import a save…* for a dynasty from the PS2 or another Xbox; and *Backups* by date. Restore single saves or a whole date; your saves become a backup first, so a restore can be undone.
* **Settings**: display mode, aspect ratio (16:9, or 4:3 with black bars at the sides), resolution (default: fullscreen at your desktop's resolution), render scale, frame rate cap, texture filtering, VSync, low latency, Xbox 720p mode; desktop shortcuts for the game ("MVP 06 Plus") and the Launcher, if you want them; and *Updates*: check for a new release, install it, or go back to the version before.

Everything is also in `mvp06-settings.toml`. Plus adds `gamecube_layout`, `gamecube_icons`, `playstation_layout`, `playstation_icons` (all on) and `save_backups` (30).

## Building from source

Windows x64 with Visual Studio's C++ tools and Windows SDK, LLVM Clang, CMake 3.25+ and Ninja. Put your Xbox files in `assets/` and run `Build-Source.cmd` from an *x64 Native Tools Command Prompt*. Details: [`docs/MVP06-HANDOFF.md`](docs/MVP06-HANDOFF.md); making a release: [`docs/RELEASING.md`](docs/RELEASING.md).

Button art by hand (Python 3 with `pip install pillow numpy scipy opencv-python-headless`):

```
python tools/ps2_layout/make_ps2_icons06.py assets/data <MVP 06 PS2 disc's DATA folder> ps2_icons
python tools/gc_layout/make_gc_icons06.py assets/data <MVP05-Plus's gc_icons folder> gc_icons
```

## Credits

* [**Mad Dog**](https://github.com/maddog847): the MVP 06 NCAA Baseball PC port this is built on.
* [**TGP482**](https://github.com/TGP482): [XboxXBERecomp](https://github.com/TGP482/XboxXBERecomp), the static recompiler for original Xbox games that the port is made with.
* **MVP06-Plus**: spy_jam.
* Third-party libraries: see `THIRD_PARTY.txt`.

## Special Thanks

* Special thanks to Mad Dog and Kccitystar for their help in the MVP community and consultation on this project.
* Also RIP to MVPmods.com and a shout out to all the community members that had done valuable work on there over the years.

## Legal

MIT licensed (`SDK-LICENSE.txt`); MVP06-Plus's additions are Copyright 2026 spy_jam under the same license. MVP 06 NCAA Baseball and its art belong to EA; none of it is included. The game's icon is made from your own Xbox disc by the Launcher. Not affiliated with or endorsed by EA, Nintendo, Sony or Microsoft. Microsoft's runtime DLLs and shader compiler are Microsoft's redistributable components, under their own terms.
