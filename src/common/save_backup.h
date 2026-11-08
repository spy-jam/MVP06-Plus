#pragma once
#include <cstdint>

// Save backups: at launch, before the game boots, the emulated hard disk's E: drive (hdd\E: UDATA, the saves,
// and TDATA, the game's own data) is copied to "save backups\<date> <time>\E" beside the exe. A launch whose
// saves are the same as the newest backup's makes none; only the newest save_backups are kept (0: off).
namespace saves {

inline uint32_t g_keep = 30;  // settings file: save_backups

void Backup();  // GameInfo::init, after the settings load: never stops the game from starting

}  // namespace saves
