#include "app/app.h"
#include "../game/gc_controls.h"
#include "save_backup.h"

// what the runtime asks of the game; strings must be set, hooks may stay null
const app::GameInfo app::kGame = {
    .title = L"MVP 06 NCAA Baseball",               // window and splash
    .short_title = L"MVP06",               // message boxes
    .name = L"MVP06",                      // window classes, crash dumps, handover event
    .log = "mvp06",                        // log file prefix
    .settings = "mvp06-settings.toml",          // settings file beside the exe
    .splash = L"splash",                  // optional splash.png or splash.bmp beside the exe
    .missing = L"The game isn't installed yet.\n\nOpen MVP06-Plus-Launcher.exe in this folder and choose your Xbox disc. "
                L"Then start the game with Launch MVP 06 there.\n\n(Or put your extracted Xbox files in the assets folder by "
                L"hand, with default.xbe directly inside it.)",
    .images = {{"default.xbe", "MVP06"}},  // each recompiled xbe and its exe, for title launches
    .options = {{"gamecube_layout", &gc::g_enabled, nullptr}, {"gamecube_icons", &gc::g_icons, nullptr},  // GameCube controllers (experimental layout on 06)
                {"playstation_layout", &gc::g_ps_enabled, nullptr}, {"playstation_icons", &gc::g_ps_icons, nullptr},  // PlayStation pads play as on PS2
                {"save_backups", nullptr, &saves::g_keep}},  // the newest saves backups kept in "save backups" (0: off)
    .load = nullptr,                      // reads more from the settings file's toml::table
    .save = nullptr,                      // writes more into it
    .init = [] {                           // after the settings load, before the window and boot
        saves::Backup();                   // the saves as they were, before this session touches them
        gc::Init();
    },
    .loaded = nullptr,                    // image in memory, before its entry point runs
    .window = gc::Window,                  // the game window is up: the button art for the controllers connected
    .message = nullptr,                   // window messages first; true takes one
    .ui = nullptr,                        // ImGui drawing each frame
    .pad = gc::Pad,                        // GameCube and PlayStation pads: buttons, pressure, stick curves
    .rumble = gc::Rumble,                  // PlayStation pads: the DualShock's two motors as the PS2 runs them
};
