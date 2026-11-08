#pragma once
#include <array>
#include <cstdint>

namespace input {
struct Pad;
}

namespace gc {
extern bool g_enabled;                   // settings file: gamecube_layout (experimental on MVP 06)
extern bool g_icons;                     // settings file: gamecube_icons
extern bool g_ps_enabled;                // settings file: playstation_layout
extern bool g_ps_icons;                  // settings file: playstation_icons
void Init();                             // GameInfo::init
void Window(void* hwnd);                 // GameInfo::window: the button art for the controllers connected
void Rumble(int port, uint16_t& left, uint16_t& right);  // GameInfo::rumble: PlayStation pads' two motors
void Pad(int port, input::Pad& pad);     // GameInfo::pad
void AfterLayout(uint32_t self);
void AfterPoll(uint32_t self);
std::array<bool, 4> g_port_gc_view();   // ports with a GameCube controller and the GameCube layout on
enum class Motor { Drop, Big, Small };
Motor PlayStationRumble(uint32_t ret, bool channel_a, float& strength, uint32_t& frames);
bool PlayStationIndex(uint32_t index);  // the game's controller index has a PlayStation pad with the PS2 layout
}  // namespace gc
