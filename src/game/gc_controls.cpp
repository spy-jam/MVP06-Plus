// MVP 06 NCAA: PlayStation pads controlling like the PS2 release (SLUS_213.67), and GameCube controllers on a
// USB adapter with an EXPERIMENTAL GameCube layout (MVP 06 had no GameCube release; the table is MVP 2005's
// GameCube one carried over, see gc_layout_table.h). Ported from the MVP 2005 mod; see MVP06-NOTES.md for the
// addresses and how each was found.
//
// Two layers, both per controller port:
//  1. Report: a GameCube controller's buttons go into the Xbox report by name (A is A, B is B, Z the white button,
//     L and R the triggers with their analog travel); a PlayStation pad's by place, with its shoulders swapped
//     back from SDL's Xbox-style mapping and its pressure carried through (PlayStation below).
//  2. Game: the pad object holds a table of 0x111 actions, each bound to one or two virtual buttons with a mode and
//     a combine rule. The Xbox layout function (0x318190, the pad's vtable +0x98) fills it for the Xbox pad; for a
//     PlayStation pad the PS2 release's table goes in its place (ps2_layout_table.h), for a GameCube controller
//     the experimental one.
//
// Pad object (vtable 0x64C518): +0x0 vtable, +0x4 + 16 * i action i {int16 a, b, mode_a, mode_b, op, pad; float
// scale}; +0x14DC the controller port; +0x1548/+0x154C rumble channel A frames/strength, +0x1550/+0x1554 channel B.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <mutex>
#include <thread>
#include <unordered_map>

#include "app/app.h"
#include "core/input.h"
#include "core/log.h"
#include "gc_controls.h"
#include "gc_layout_table.h"
#include "ps2_layout_table.h"
#include "xdk/hle.h"

using namespace kernel;

namespace gc {

bool g_enabled = true;     // settings file: gamecube_layout (experimental on MVP 06)
bool g_icons = true;       // settings file: gamecube_icons
bool g_ps_enabled = true;  // settings file: playstation_layout
bool g_ps_icons = true;    // settings file: playstation_icons

void Init() {}

// Button art. gc_icons and ps2_icons beside the exe hold the game's own files rebuilt with GameCube or PS2 button
// icons (tools/gc_layout, tools/ps2_layout); the chosen folder's files replace the disc's at the same paths. The art
// is read as the game loads it, so it follows the controllers connected at start: a GameCube controller gives the
// GameCube's, else a PlayStation pad the PS2's.
std::atomic<bool> g_booting{false};  // Window's polls, before the game is in memory

void Window(void*) {
    bool gamecube = false, playstation = false;
    g_booting = true;
    // the adapter's thread finds its controllers within a few of its reports
    for (int tries = 0; tries < 40 && !gamecube; tries++) {
        for (int port = 0; port < 4; port++) {
            input::Pad p = input::Poll(port);
            gamecube |= p.connected && p.gc.present;
            playstation |= p.connected && p.playstation;
        }
        if (!gamecube) std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    g_booting = false;
    const char* folder = gamecube && g_enabled && g_icons             ? "gc_icons"
                         : playstation && g_ps_enabled && g_ps_icons ? "ps2_icons"
                                                                      : nullptr;
    std::error_code ec;
    if (folder) {
        auto dir = app::ExeDir() / folder;
        if (std::filesystem::is_directory(dir, ec)) kernel::SetDiscOverlay(dir);
        else LOGR("gc: no %s folder beside the exe, the button icons stay the Xbox ones", folder);
    }
}

namespace {

constexpr uint32_t kPadVtable = 0x64C518;  // the local controller's pad class (0x64C458 is its stub base)
constexpr uint32_t kTable = 0x4;
constexpr uint32_t kEntries = 0x111;
constexpr uint32_t kPortField = 0x14DC;    // XInputOpen's port (0x317600)
constexpr uint32_t kPadList = 0x6D5A04;    // pads at [list] + 0xC + 4 * index (the rumble wrappers' index)
constexpr uint32_t kPadListSize = 6;       // the list holds 6 (0x28EA50 clears 0x18 bytes)

std::atomic<bool> g_port_gc[4];
std::atomic<bool> g_port_ps[4];  // a PlayStation pad, with the PS2 layout on

enum class Layout { Xbox, GameCube, PlayStation };
struct PadObject {
    std::array<uint8_t, kEntries * 16> xbox{};  // the table as the Xbox layout left it
    bool have_xbox = false;
    Layout layout = Layout::Xbox;  // the table in place
};
std::mutex g_lock;
std::unordered_map<uint32_t, PadObject> g_pads;

Layout Wanted(uint32_t self) {
    uint32_t port = R32(self + kPortField);
    if (port >= 4) return Layout::Xbox;
    if (g_enabled && kHaveGcTable && g_port_gc[port]) return Layout::GameCube;
    if (g_port_ps[port]) return Layout::PlayStation;
    return Layout::Xbox;
}

void WriteTable(uint32_t self, const Entry* table, uint32_t count) {
    static_assert(kGcEntries <= kEntries && ps::kPsEntries <= kEntries);
    for (uint32_t i = 0; i < count; i++) {
        const Entry& e = table[i];
        uint32_t at = self + kTable + 16 * i;
        W16(at + 0, uint16_t(e.a));
        W16(at + 2, uint16_t(e.b));
        W16(at + 4, uint16_t(e.mode_a));
        W16(at + 6, uint16_t(e.mode_b));
        W16(at + 8, uint16_t(e.op));
        float s = e.scale;
        std::memcpy(HostPtr(at + 12), &s, 4);
    }
}

// the table to match the controller now on the object's port
void Sync(uint32_t self, PadObject& o) {
    Layout want = Wanted(self);
    if (want == o.layout || !o.have_xbox) return;
    if (want == Layout::GameCube) WriteTable(self, kGcTable, kGcEntries);
    else if (want == Layout::PlayStation) WriteTable(self, ps::kPsTable, ps::kPsEntries);
    else std::memcpy(HostPtr(self + kTable), o.xbox.data(), o.xbox.size());
    o.layout = want;
    LOGR("gc: port %u now has the %s layout", R32(self + kPortField) + 1,
         want == Layout::GameCube ? "GameCube (experimental)" : want == Layout::PlayStation ? "PS2" : "Xbox");
}

// Stick response. Both releases shape the sticks with the same code, in one of two modes set by the screen
// (Xbox 0x6ABA18, PS2 0x833E54):
//  - 0, the menus: each of a stick's four directions on its own, nothing below 0.7, then (v - 0.7) * 3.33; the same
//    on every release, so the stick goes to the Xbox read as it is;
//  - else, play: the tilt m (capped at 1) gives s = (m - 0.4) / 0.6 on the Xbox (its pad read, 0x317B60), each axis
//    clamp(axis * s, -1, 1), nothing below m = 0.4. A stick handed to the Xbox read is chosen so that its curve comes
//    out at the PS2's or the GameCube's.
// The triggers and face buttons go through the Xbox's per-channel table (0x6B0B04, filled by 0x4CB3E0: face buttons
// and White/Black (v - 0.3) x 1.43, the triggers (v - 0.4) x 1.67), as in MVP 2005.
constexpr uint32_t kStickMode = 0x6ABA18;

// the stick to hand the Xbox read (play mode) for it to come out as (ox, oy)
void XboxStickFor(float ox, float oy, int16_t& ix, int16_t& iy) {
    float n = std::sqrt(ox * ox + oy * oy);
    if (n == 0.0f) {
        ix = iy = 0;
        return;
    }
    if (n <= 1.0f) {
        // Xbox output length for an input of length k (0.4 <= k <= 1) is k (k - 0.4) / 0.6: solve it for n
        float k = 0.2f + std::sqrt(0.04f + 0.6f * n);
        ox = ox / n * k;
        oy = oy / n * k;
    }
    // past length 1 the Xbox caps the factor at 1 and passes each axis through as it is
    auto i16 = [](float v) { return int16_t(std::clamp(v * 32768.0f, -32767.0f, 32767.0f)); };
    ix = i16(ox);
    iy = i16(oy);
}

// The GameCube stick, as the MVP 2005 GameCube release shaped it (no dead zone, factor m + 0.2; see the 2005 mod).
// MVP 06 had no GameCube release: this keeps the GameCube feel from 2005.
void GameCubeStick(int16_t& ix, int16_t& iy) {
    float x = ix / 32768.0f, y = iy / 32768.0f;
    float m = std::sqrt(x * x + y * y);
    if (m == 0.0f) return;
    float s = std::min(m, 1.0f) + 0.2f;
    XboxStickFor(std::clamp(x * s, -1.0f, 1.0f), std::clamp(y * s, -1.0f, 1.0f), ix, iy);
}

// The PS2's play-mode curve (ps2pad update fn_001011B0, mode != 0; the same as MVP 2005's): the stick's byte less 127,
// nothing inside radius 51, the tilt m capped at 127, each direction (m - 51) * 2 / 76 times the axis, capped at 255.
// SDL's PlayStation drivers give the pad's bytes as b * 257 - 32768.
void PlayStationStick(int16_t& ix, int16_t& iy) {
    float x = (int(ix) + 32768) / 257.0f - 127.0f;   // right
    float y = (32767 - int(iy)) / 257.0f - 127.0f;   // down (iy is y up, SDL's axis -1 - iy)
    float m2 = x * x + y * y;
    if (m2 < 2601.0f) {
        ix = iy = 0;
        return;
    }
    float s = (std::min(std::sqrt(m2), 127.0f) - 51.0f) * 2.0f / 76.0f;
    float ox = std::clamp(x * s, -255.0f, 255.0f) / 255.0f, oy = std::clamp(-y * s, -255.0f, 255.0f) / 255.0f;
    XboxStickFor(ox, oy, ix, iy);
}

// the pad object at the game's controller index (the rumble wrappers' first argument), or 0
uint32_t PadAt(uint32_t index) {
    if (index >= kPadListSize) return 0;
    uint32_t list = R32(kPadList);
    if (!list) return 0;
    uint32_t pad = R32(list + 0xC + 4 * index);
    return pad && R32(pad) == kPadVtable ? pad : 0;
}

int PortOfPad(uint32_t pad) {
    if (!pad) return -1;
    uint32_t port = R32(pad + kPortField);
    return port < 4 ? int(port) : -1;
}

}  // namespace

std::array<bool, 4> g_port_gc_view() { return {g_port_gc[0], g_port_gc[1], g_port_gc[2], g_port_gc[3]}; }

// A PlayStation pad, as the PS2 release lays it out: every button where the Xbox has the one in the same place,
// but its shoulders the other way round from SDL's Xbox-style mapping: L1 and R1 (SDL's shoulders) go on the
// Xbox triggers' channels, L2 and R2 (SDL's triggers, with their travel) on White and Black. With the PS2's own
// action table on top, each button does what it does on the PS2.
// Pressure: the PS2 game reads Cross, Circle, Square, Triangle and the four shoulders as 0-255 with nothing taken
// off (fn_001011B0 copies the pressure bytes; fn_00105990: byte / 255). The Xbox read takes a dead zone off its
// analog channels (0x6B0B04), so a pressure p goes in as t + p / k to come out of it as p. (The D-pad stays digital,
// as the Xbox pad's is.)
uint8_t Through(uint8_t p, float t, float k) {
    if (!p) return 0;
    return uint8_t(std::min(255L, std::lround(255.0f * t + float(p) / k)));
}

// A pressed button whose pressure reads 0 is on a pad or adapter that reports the pressure channels without filling
// them: it counts as fully pressed.
uint8_t Pressure(uint8_t pressure, uint8_t digital) { return pressure ? pressure : digital ? 0xFF : 0; }

void PlayStation(input::Pad& p) {
    uint8_t l1 = p.analog[5], r1 = p.analog[4];  // SDL's left and right shoulder, as input.cpp puts them
    uint8_t l2 = p.analog[6], r2 = p.analog[7];  // and its triggers, with their travel
    if (p.has_pressure) {
        for (int i = 0; i < 4; i++) p.analog[i] = Through(Pressure(p.pressure[i], p.analog[i]), 0.3f, 1.0f / 0.7f);
        l1 = Through(Pressure(p.pressure[4], l1), 0.4f, 1.0f / 0.6f);
        r1 = Through(Pressure(p.pressure[5], r1), 0.4f, 1.0f / 0.6f);
    }
    // L2 and R2 read from their first touch, as the PS2 reads them
    p.analog[5] = Through(l2, 0.3f, 1.0f / 0.7f);  // White: L2
    p.analog[4] = Through(r2, 0.3f, 1.0f / 0.7f);  // Black: R2
    p.analog[6] = l1;                              // the triggers: L1 and R1
    p.analog[7] = r1;
    if (R32(kStickMode) != 0) {  // play: the PS2's curve; menus: as it is
        PlayStationStick(p.lx, p.ly);
        PlayStationStick(p.rx, p.ry);
    }
}

void Pad(int port, input::Pad& p) {
    if (port < 0 || port > 3) return;
    g_port_gc[port] = p.connected && p.gc.present && g_enabled;
    g_port_ps[port] = p.connected && !p.gc.present && p.playstation && g_ps_enabled;
    if (g_booting) return;  // the stick mode below is the game's memory, not there yet
    if (g_port_ps[port]) PlayStation(p);
    if (!g_port_gc[port]) return;
    using G = input::GameCube;
    const input::GameCube& c = p.gc;
    auto on = [&](uint16_t b) { return (c.buttons & b) != 0; };
    p.buttons = uint16_t(on(G::Up) << 0 | on(G::Down) << 1 | on(G::Left) << 2 | on(G::Right) << 3 | on(G::Start) << 4);
    p.analog[0] = on(G::A) ? 0xFF : 0;
    p.analog[1] = on(G::B) ? 0xFF : 0;
    p.analog[2] = on(G::X) ? 0xFF : 0;
    p.analog[3] = on(G::Y) ? 0xFF : 0;
    p.analog[4] = 0;                    // black: no GameCube button
    p.analog[5] = on(G::Z) ? 0xFF : 0;  // white
    p.analog[6] = c.l;
    p.analog[7] = c.r;
    p.lx = c.lx;
    p.ly = c.ly;
    p.rx = c.cx;
    p.ry = c.cy;
    if (R32(kStickMode) != 0) {
        GameCubeStick(p.lx, p.ly);
        GameCubeStick(p.rx, p.ry);
    }
}

// after the Xbox layout function: keep its table, then put the port's one in
void AfterLayout(uint32_t self) {
    if (R32(self) != kPadVtable) return;
    std::lock_guard lock(g_lock);
    PadObject& o = g_pads[self];
    std::memcpy(o.xbox.data(), HostPtr(self + kTable), o.xbox.size());
    o.have_xbox = true;
    o.layout = Layout::Xbox;
    Sync(self, o);
}

// after each read: a controller plugged into or pulled from the port changes the table with it
void AfterPoll(uint32_t self) {
    if (R32(self) != kPadVtable) return;
    std::lock_guard lock(g_lock);
    auto it = g_pads.find(self);
    if (it != g_pads.end()) Sync(self, it->second);
}

// Rumble. The game asks through two wrappers, cdecl (controller index, on, strength, frames):
//   0x28E8E0 for channel A (pad vtable +0x54: strength as given at +0x154C)
//   0x28E870 for channel B (pad vtable +0x58: strength clamped to 0..1 at +0x1554)
// The pad's update (0x317700) counts each channel's frames down and, every frame something changed, sends one level
// to both of the controller's motors: A x 65535, plus 16348 + B x 8192 while B is on, capped at 65535.
// The PS2 (wrappers fn_00455E20 big motor, fn_00455F10 small motor) runs the DualShock's two motors apart: the big
// one at a strength, the small one on or off (on from 0.5). Its events, against the Xbox's (MVP06-NOTES.md):
//   call returns to   Xbox                                  PS2
//   0x29FEC4  A       pitch cursor clamp(.27v+.13,.13,.4) 1  big clamp(.25v+.35,.35,.6), 2 frames
//   0x18B978  A       fielding (with B, 0x18B982)           (dropped: the PS2 asks the big motor once)
//   0x18B982  B       fielding .4 + .6x                     big .6 + .3x, the same frames
//   0xA2459   A       fielding (with B, 0xA244F)            (dropped)
//   0xA244F   B       fielding .4 + .6x                     big .6 + .3x
//   0x1947D1  A       batter's right stick held up, 1.0 x1   small on, 2 frames
//   0x1947E0  B       (its other half) 1.0 x1               big 1.0, 2 frames
//   0x20FF76  A       co-op runner cue 1.0 x1                small on, 2 frames
//   0x244E37  A       0.3, timed                             big 0.3, the same frames
//   0x1D7019  B       impact clamp(.01v,.5,1), 5             the same, big
//   0x640A9   B       vibration test / menu, 1.0             the same, big
// So for a PlayStation player every big-motor event goes through channel B, every small-motor event through A, and
// the motor output (Rumble below) reads the two channels back: B's strength on the big motor, A's on the small.
Motor PlayStationRumble(uint32_t ret, bool channel_a, float& strength, uint32_t& frames) {
    switch (ret) {
    case 0x29FEC4: {
        float v = (strength - 0.13f) / 0.27f;
        strength = std::clamp(0.25f * v + 0.35f, 0.35f, 0.6f);
        frames = 2;
        return Motor::Big;
    }
    case 0x18B978: case 0xA2459: return Motor::Drop;
    case 0x18B982: case 0xA244F: strength = 0.6f + 0.3f * (strength - 0.4f) / 0.6f; return Motor::Big;
    case 0x1947D1: case 0x20FF76: strength = 1.0f; frames = 2; return Motor::Small;
    case 0x1947E0: strength = 1.0f; frames = 2; return Motor::Big;
    default:
        (void)channel_a;
        return Motor::Big;  // everything else the PS2 sends to the big motor, at the Xbox's strength
    }
}

bool PlayStationIndex(uint32_t index) {
    int port = PortOfPad(PadAt(index));
    return port >= 0 && g_port_ps[port].load();
}

// The motor output for a PlayStation pad: the two channels the Xbox update mixed, apart again. Called with the level
// the update sends; a level of 0 (nothing on, or the update's 10 s cutoff) stays 0.
void Rumble(int port, uint16_t& left, uint16_t& right) {
    if (port < 0 || port > 3 || !g_port_ps[port]) return;
    if (!left && !right) return;
    for (uint32_t i = 0; i < kPadListSize; i++) {
        uint32_t pad = PadAt(i);
        if (PortOfPad(pad) != port) continue;
        float a, b;
        std::memcpy(&a, HostPtr(pad + 0x154C), 4);
        std::memcpy(&b, HostPtr(pad + 0x1554), 4);
        left = uint16_t(std::lround(std::clamp(b, 0.0f, 1.0f) * 65535.0f));  // the big (low-frequency) motor
        right = a >= 0.5f ? 0xFFFF : 0;                                      // the small one, on or off
        return;
    }
}

}  // namespace gc

// rumble requests (cdecl: controller index, on, strength, frames); see gc::PlayStationRumble
X86_EXTERN_FUNC(__imp__sub_0028E870);
X86_EXTERN_FUNC(__imp__sub_0028E8E0);
static void RumbleWrapper(X86Context& ctx, uint8_t* base, bool channel_a) {
    uint32_t ret = R32(ctx.esp), index = R32(ctx.esp + 4), strength_at = ctx.esp + 12, frames_at = ctx.esp + 16;
    if (!gc::PlayStationIndex(index)) {
        channel_a ? __imp__sub_0028E8E0(ctx, base) : __imp__sub_0028E870(ctx, base);
        return;
    }
    uint32_t bits = R32(strength_at), frames = R32(frames_at), f = frames;
    float s;
    std::memcpy(&s, &bits, 4);
    gc::Motor m = gc::PlayStationRumble(ret, channel_a, s, f);
    if (m == gc::Motor::Drop) {
        ::kernel::Return(ctx, 0, 0);
        return;
    }
    uint32_t nb;
    std::memcpy(&nb, &s, 4);
    W32(strength_at, nb);
    W32(frames_at, f);
    if (m == gc::Motor::Small) __imp__sub_0028E8E0(ctx, base);  // channel A: the small motor
    else __imp__sub_0028E870(ctx, base);                       // channel B: the big motor
    W32(strength_at, bits);  // cdecl: the caller's arguments, put back
    W32(frames_at, frames);
}
X86_FUNC(sub_0028E870) { RumbleWrapper(ctx, base, false); }
X86_FUNC(sub_0028E8E0) { RumbleWrapper(ctx, base, true); }

// the pad's layout (vtable +0x98), called at the end of the game's default action table (0x28B1D0)
X86_EXTERN_FUNC(__imp__sub_00318190);
X86_FUNC(sub_00318190) {
    uint32_t self = ctx.ecx;
    __imp__sub_00318190(ctx, base);
    gc::AfterLayout(self);
}

// the pad's read (vtable +0xA4): XInputGetState into the channels, the stick curve and the per-channel table
X86_EXTERN_FUNC(__imp__sub_00317B60);
X86_FUNC(sub_00317B60) {
    uint32_t self = ctx.ecx;
    __imp__sub_00317B60(ctx, base);
    gc::AfterPoll(self);
}
