# MVP06-Plus Beta 2

Bring your dynasty over from the PS2, update from the Launcher, and a tidier Launcher, from MVP05-Plus Beta 2's work.

## Highlights
- **Import dynasties** (*Saves → Import a save…*): a dynasty from the PS2 or another Xbox, converted into one of your MVP06-Plus dynasty saves. Your save is backed up first.
- **Updates from the Launcher** (*Settings → Updates*): check, install and undo, from this version on.
- **Low latency** (*Settings*, off by default): less delay between a button and the screen.

## Import dynasties
*Saves → Your saves → Import a save…*: choose the dynasty, pick which of your dynasty saves it goes into (it's backed up first, in *Saves → Backups*), and import. Start a dynasty in the game and save it once, so you have a dynasty save to import into.
- **PS2:** from a `.psu`, a PCSX2 memory card (`.ps2`: you pick the save on it), or the `.sav` from a save.
- **Xbox:** from another Xbox (its `data.dat`).

PS2 dynasty conversion is **spy_jam**'s.

## Launcher
- **Updates** (*Settings → Updates*): shows your version, checks GitHub for a newer release (also when the Launcher opens, unless you turn that off), shows what's new and installs it: the program files only, checked against the release's manifest. Your game files, saves, backups, button art and shader cache are never touched, and your settings are kept, with new options added. *Back to …* undoes the last update.
- **A tidier layout:** *Saves* switches between your saves and backups, and *Settings* has desktop shortcuts and updates side by side.
- **Your game's title art** on the *Play* tab, from your own Xbox disc.
- **Controllers:** an Xbox-style controller, or a GameCube controller on the adapter (with its WinUSB driver), moves around the Launcher: d-pad or stick, A presses, B goes back, LB / RB (L / R) switch tabs, Start launches the game from *Play*.
- **Bring over an older install:** the first time the Launcher opens in a new folder (or on Ctrl+Shift+B), it offers to bring MVP06-Plus Beta 1 or Mad Dog's MVP06 over: its game, saves and settings, copied or moved in.

## Game
- **Low latency** (*Settings*, off by default): one finished frame waits for the screen instead of up to three, for up to about two frames (~33 ms at 60 Hz) less delay between a button and the screen. It can stutter on a slower PC, so it starts off.

## Fixed
- The Launcher's *Settings* no longer drops the note after a text setting (such as `display_mode`) in `mvp06-settings.toml`.

## Coming from Beta 1 or Mad Dog's MVP06
Unzip MVP06-Plus into a new folder and open the Launcher. It asks to bring over your game, saves and settings, so you don't need your discs again. Said no? Press **Ctrl+Shift+B** in the Launcher to be asked again. From Beta 2 on, *Settings → Updates* updates MVP06-Plus for you.

## Thanks
**Mad Dog** for MVP06, and **TGP482** for XboxXBERecomp.

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
