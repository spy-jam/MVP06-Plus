#pragma once
#include <cstdint>

namespace input {

// a GameCube controller on a Wii U / Switch GameCube adapter, as the adapter reports it
struct GameCube {
    enum : uint16_t {
        A = 1 << 0, B = 1 << 1, X = 1 << 2, Y = 1 << 3, Z = 1 << 4, Start = 1 << 5,
        Up = 1 << 6, Down = 1 << 7, Left = 1 << 8, Right = 1 << 9,
        LClick = 1 << 10, RClick = 1 << 11,  // the triggers' digital click at the bottom of their travel
    };
    bool present = false;
    uint16_t buttons = 0;
    int16_t lx = 0, ly = 0, cx = 0, cy = 0;  // y up, as the console's report
    uint8_t l = 0, r = 0;                    // analog trigger travel 0-255
};

// the console controller's report, analog buttons are 0-255
struct Pad {
    bool connected = false;
    uint16_t buttons = 0;  // dpad up/down/left/right, start, back, left thumb, right thumb
    uint8_t analog[8] = {};  // A B X Y black white left trigger right trigger
    int16_t lx = 0, ly = 0, rx = 0, ry = 0;
    bool playstation = false;  // a DualShock 3, DualShock 4 or DualSense (by SDL's gamepad type)
    // pressure-sensitive buttons (a DualShock 3, or a PS2 pad on an adapter that reports as one), 0-255:
    // Cross Circle Square Triangle L1 R1 Up Down Left Right
    bool has_pressure = false;
    uint8_t pressure[10] = {};
    GameCube gc;  // filled as well when the port's controller is a GameCube controller
};

void Init();  // window thread, before boot
// the controller on that port, then GameInfo::pad
Pad Poll(int port);
void Rumble(int port, uint16_t left, uint16_t right);

}  // namespace input
