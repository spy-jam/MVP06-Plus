#pragma once
#include <cstdint>

namespace input {
struct GameCube;
}

// The Nintendo Wii U / Switch GameCube controller adapter (WUP-028, USB 057E:0337), read directly: through WinUSB
// when the adapter has the WinUSB driver (Zadig, as for Dolphin), else through the Windows HID driver.
namespace gcadapter {

void Start();                                // once; a thread finds the adapter, reads it and reopens it when replugged
bool Read(int slot, input::GameCube& out);  // adapter port 0-3; false when nothing is plugged into it
void Rumble(int slot, bool on);

}  // namespace gcadapter
