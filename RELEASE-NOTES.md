# MVP06-Plus Beta 1

First release of MVP06-Plus by spy_jam, built on Mad Dog's MVP06 Public Beta 1 (made with TGP482's XboxXBERecomp).

## New
- **PlayStation controllers** with the PS2 release's full control layout and stick handling, analog button pressure and rumble.
- **GameCube controllers (experimental)** through a Wii U / Switch GameCube adapter (official or compatible, in Wii U mode), all 4 ports, with rumble. Stick, C-stick and triggers handled as on GameCube. There was no GameCube MVP 06, so the layout follows MVP 2005's GameCube release as closely as 06 allows. Hold X + Y + Start for 3 seconds to recentre.
- **Button art:** PS2 or GameCube button pictures in menus, help bars and in-game, picked from the controller connected at start. PS2 art is made from your own MVP 06 PS2 disc; GameCube art from MVP 2005's, made from your 2005 GameCube and Xbox discs or taken from your MVP05-Plus folder (both optional).
- **MVP06-Plus Launcher** (`MVP06-Plus-Launcher.exe`): installs the Xbox game into `assets/` and makes the button art, then opens on *Play*, with Launch and which controllers Windows sees, including whether the GameCube adapter has its WinUSB driver. Also *Saves* and *Settings* (display mode, aspect ratio, resolution and more, and desktop shortcuts if you want them). Portable: everything stays in the game folder.
- **Shader cache** in `shader_cache/`, so shaders compile once instead of every run.
- **The game's icon**, made from your own Xbox disc by the Launcher.
- **Save backups** at startup, in `save backups/` (30 kept by default), listed in the Launcher's *Saves* tab, where you can restore single saves or a whole date.
- **Esc quits** after asking (Alt+F4 still works). Don't quit while the game is saving.
- **Fullscreen by default**, at your desktop's own resolution (Mad Dog's release starts borderless at 1920 x 1080); change it in the Launcher's *Settings* tab.

## Fixed
- SteamOS (through Proton): the black screen; the GameCube adapter through `gcbridge` (see the README for the launch option).

## Known issues
- Under Proton, the GameCube adapter needs the Steam launch option; the game can't start `gcbridge` by itself yet.

## Requirements
Windows 10/11 x64 (or SteamOS with Proton), a DirectX 12 graphics card, a few GB free, and your own MVP 06 NCAA Baseball Xbox disc image. The PS2 disc and the 2005 discs (or MVP05-Plus) are optional, for button art. Nothing else to install.
