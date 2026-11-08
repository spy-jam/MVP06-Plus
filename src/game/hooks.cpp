// Diagnostic wrappers and narrowly scoped, evidence-backed game hooks.
#include "xdk/hle.h"
#include "core/log.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <chrono>
#include "pregame_speech_gate.h"

// Observe the title's actual mode selection, without overriding its return values.
X86_EXTERN_FUNC(__imp__sub_0031D913);
X86_FUNC(sub_0031D913) {
    const uint32_t caller = kernel::R32(ctx.esp);
    __imp__sub_0031D913(ctx, base);
    static std::atomic<unsigned> count{0};
    if (count.fetch_add(1) < 8)
        LOGR("video mode: XGetVideoFlags caller=%08X result=%08X", caller, ctx.eax);
}

X86_EXTERN_FUNC(__imp__sub_002DC0A0);
X86_FUNC(sub_002DC0A0) {
    const uint32_t object = ctx.ecx;
    __imp__sub_002DC0A0(ctx, base);
    LOGR("video mode: title display initialized dimensions=%ux%u flags21C=%u flags21D=%u",
         kernel::R32(object+0x0C), kernel::R32(object+0x10),
         unsigned(X86_MEM8(object+0x21C)), unsigned(X86_MEM8(object+0x21D)));
}

X86_EXTERN_FUNC(__imp__sub_0003E830);
X86_FUNC(sub_0003E830) {
    const bool loading_check = kernel::R32(ctx.esp) == 0x00128EDF;
    // Match the validated stock call bytes and certificate before overriding AL.
    const uint32_t certificate = kernel::R32(0x00010118);
    const bool matching_game = certificate && kernel::R32(certificate+8) == 0x4541008D &&
        kernel::R32(0x00128EDA) == 0xF15951E8 && X86_MEM8(0x00128EDE) == 0xFF;
    __imp__sub_0003E830(ctx, base);
    if (!loading_check || !matching_game) return;
    // This guest function returns a Boolean in AL; upper EAX bits are not status.
    const bool active = (ctx.eax & 0xFF) != 0;
    using namespace std::chrono;
    const uint64_t now = duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
    static thread_local PregameSpeechGate gate;
    const bool new_session = !gate.initialized || now - gate.last_ms > 1000;
    const bool was_active = gate.saw_active;
    const bool held = gate.Hold(now, active);
    if (new_session) LOGR("pregame speech gate: waiting for narration (10 second limit)");
    if (active && (!was_active || new_session)) LOGR("pregame speech gate: narration started after %llu ms", static_cast<unsigned long long>(now-gate.first_ms));
    if (!held && !active && !gate.saw_active) {
        static thread_local uint64_t reported_session = 0;
        if (reported_session != gate.first_ms) { reported_session=gate.first_ms; LOGR("pregame speech gate: timed out; original status restored"); }
    }
    if (held) ctx.eax = (ctx.eax & 0xFFFFFF00u) | 1;
}
#define TRACE_MOVIE(addr) \
X86_EXTERN_FUNC(__imp__sub_##addr); \
X86_FUNC(sub_##addr) { \
    static std::atomic<unsigned> count{0}; \
    bool trace = count.fetch_add(1) < 6; \
    if (trace) LOGR("movie enter " #addr " caller=%08X", X86_MEM32(ctx.esp)); \
    __imp__sub_##addr(ctx, base); \
    if (trace) LOGR("movie leave " #addr " eax=%08X", ctx.eax); \
}
TRACE_MOVIE(0041E65A)
TRACE_MOVIE(0049ADDE)
TRACE_MOVIE(00494B38)
TRACE_MOVIE(0049E807)

// Observe frontend transitions without forcing screens or adding delays.
X86_EXTERN_FUNC(__imp__sub_000E4850);
X86_FUNC(sub_000E4850) {
    using kernel::R32;
    uint32_t object = ctx.ecx, text = R32(ctx.esp+4), caller = R32(ctx.esp);
    char event[32] = {};
    if (text) for (unsigned i=0;i<31;++i) { event[i]=char(X86_MEM8(text+i)); if (!event[i]) break; }
    static std::atomic<unsigned> count{0};
    bool trace = event[0] && count.fetch_add(1) < 180;
    uint32_t before = R32(object+0xBC);
    if (trace) LOGR("frontend event: name=%s caller=%08X object=%08X screen=%08X source=%08X countdown=%d pending=%u", event, caller, object, before, R32(ctx.esp+8), int32_t(R32(object+0x38)), unsigned(X86_MEM8(object+0xC8)));
    __imp__sub_000E4850(ctx,base);
    if (trace) LOGR("frontend result: screen=%08X previous=%08X pending=%u", R32(object+0xBC), R32(object+0xC0), unsigned(X86_MEM8(object+0xC8)));
}
X86_EXTERN_FUNC(__imp__sub_0010B720);
X86_EXTERN_FUNC(__imp__sub_000C8920);
X86_FUNC(sub_000C8920) {
    uint32_t object=ctx.ecx;
    LOGR("matchup setup: object=%08X clock=%u", object, kernel::R32(0x006C6814));
    __imp__sub_000C8920(ctx,base);
    uint32_t handle=kernel::R32(object+0x200);
    LOGR("matchup setup result: result=%u handle=%08X active=%u timer=%08X", ctx.eax&255, handle, handle ? unsigned(X86_MEM8(handle+4)) : 0, handle ? kernel::R32(handle+0x18) : 0);
}
X86_FUNC(sub_0010B720) {
    using kernel::R32;
    uint32_t object = ctx.ecx, handle = R32(object+0x200);
    static std::atomic<unsigned> count{0};
    if (count.fetch_add(1)<80) LOGR("matchup update: object=%08X handle=%08X active=%u flags=%08X", object, handle, handle ? unsigned(X86_MEM8(handle+4)) : 0, R32(object+0x4C));
    __imp__sub_0010B720(ctx,base);
}

// Unhandled Xbox audio-control exports: observe arguments/results before fixing.
#define TRACE_AUDIO_CONTROL(addr) \
X86_EXTERN_FUNC(__imp__sub_##addr); \
X86_FUNC(sub_##addr) { \
    static std::atomic<unsigned> count{0}; \
    bool trace = count.fetch_add(1) < 24; \
    if (trace) LOGR("audio control " #addr " caller=%08X args=%08X,%08X,%08X,%08X", kernel::R32(ctx.esp), kernel::R32(ctx.esp+4), kernel::R32(ctx.esp+8), kernel::R32(ctx.esp+12), kernel::R32(ctx.esp+16)); \
    __imp__sub_##addr(ctx, base); \
    if (trace) LOGR("audio control " #addr " result=%08X", ctx.eax); \
}
TRACE_AUDIO_CONTROL(005C09A9)
TRACE_AUDIO_CONTROL(005C0A56)
// These native EA routines contain the buffer Play call sites. Observe only.
TRACE_AUDIO_CONTROL(00433C67)
TRACE_AUDIO_CONTROL(004349DD)

// Loading-card thread lifecycle (separate from in-game TEAMSMATCHUP overlays).
TRACE_AUDIO_CONTROL(0042088E)
TRACE_AUDIO_CONTROL(00420A50)
X86_EXTERN_FUNC(__imp__sub_00130780);
X86_FUNC(sub_00130780) {
    uint32_t object=ctx.ecx;
    LOGR("loading card start: object=%08X mode=%u rate=%u",object,kernel::R32(ctx.esp+4),kernel::R32(ctx.esp+8));
    __imp__sub_00130780(ctx,base);
    LOGR("loading card start result: ok=%u thread=%08X done=%u",ctx.eax&255,kernel::R32(object+4),unsigned(X86_MEM8(object+0x14)));
}
X86_EXTERN_FUNC(__imp__sub_0012C920);
X86_FUNC(sub_0012C920) {
    uint32_t object=ctx.ecx;
    LOGR("loading card thread enter: object=%08X done=%u",object,unsigned(X86_MEM8(object+0x14)));
    __imp__sub_0012C920(ctx,base);
    LOGR("loading card thread exit: object=%08X done=%u loaded=%u frames=%u",object,unsigned(X86_MEM8(object+0x14)),unsigned(X86_MEM8(object+0x58)),kernel::R32(object+0x70));
}
X86_EXTERN_FUNC(__imp__sub_00128E90);
X86_FUNC(sub_00128E90) {
    uint32_t object=ctx.ecx;
    static std::atomic<unsigned> count{0};
    bool trace=count.fetch_add(1)<12;
    if(trace) LOGR("loading card tick: done=%u loaded=%u speechSeen=%u frames=%u",unsigned(X86_MEM8(object+0x14)),unsigned(X86_MEM8(object+0x58)),unsigned(X86_MEM8(object+0x6C)),kernel::R32(object+0x70));
    __imp__sub_00128E90(ctx,base);
    if(trace) LOGR("loading card tick result: done=%u",unsigned(X86_MEM8(object+0x14)));
}
TRACE_AUDIO_CONTROL(00128E10)

// Follow only the codec-4 stream callback; do not change decoding or queue state.
static thread_local bool tracing_codec4 = false;
static std::atomic<uint32_t> speech_voice{0};
X86_EXTERN_FUNC(__imp__sub_0043A3E2);
X86_FUNC(sub_0043A3E2) {
    using kernel::R32;
    static std::atomic<unsigned> count{0};
    unsigned sequence = count.fetch_add(1);
    bool trace = sequence < 80 || (sequence < 10000 && sequence % 500 == 0);
    uint32_t decoder = R32(ctx.esp + 4), requested = R32(ctx.esp + 8);
    uint32_t output = R32(ctx.esp + 16);
    bool previous = tracing_codec4;
    tracing_codec4 = trace;
    if (trace) LOGR("EA speech pull: decoder=%08X requested=%u stream=%u pending=%u revision=%u", decoder, requested, R32(decoder+0x24), R32(decoder+0x28), R32(decoder+0x30));
    uint32_t voice = speech_voice.load();
    if (trace && voice && R32(voice+0x48) == decoder) LOGR("EA speech mixer: state=%08X gains=%08X,%08X,%08X targets=%08X,%08X,%08X", R32(voice), R32(voice+4), R32(voice+8), R32(voice+12), R32(voice+0x1C), R32(voice+0x20), R32(voice+0x24));
    __imp__sub_0043A3E2(ctx, base);
    if (trace) LOGR("EA speech result: produced=%d chunk=%08X length=%u", int32_t(ctx.eax), R32(decoder+0x1C), R32(decoder+0x20));
    if (ctx.eax > 0 && ctx.eax <= requested && requested <= 4096) {
        double peak = 0;
        unsigned nonzero = 0, invalid = 0;
        for (uint32_t i = 0; i < ctx.eax; ++i) {
            uint32_t bits = R32(output + i*4);
            float sample;
            std::memcpy(&sample, &bits, 4);
            if (!std::isfinite(sample)) ++invalid;
            else { if (sample != 0) ++nonzero; if (std::abs(double(sample)) > peak) peak = std::abs(double(sample)); }
        }
        if (trace) LOGR("EA speech samples: count=%u nonzero=%u invalid=%u peak=%g first=%08X", ctx.eax, nonzero, invalid, peak, R32(output));
        // Bounded local float capture, independent of host audio configuration.
        static FILE* capture = std::fopen("boot-evidence/speech-samples.f32", "wb");
        static uint32_t captured = 0;
        if (capture && captured + ctx.eax <= 480000) {
            for (uint32_t i = 0; i < ctx.eax; ++i) { uint32_t bits = R32(output+i*4); std::fwrite(&bits, 4, 1, capture); }
            captured += ctx.eax;
            std::fflush(capture);
        }
    }
    tracing_codec4 = previous;
}
X86_EXTERN_FUNC(__imp__sub_00430010);
X86_FUNC(sub_00430010) {
    using kernel::R32;
    uint32_t stream = R32(ctx.esp+4), channel = R32(ctx.esp+8), length = R32(ctx.esp+12), flag = R32(ctx.esp+16);
    if (tracing_codec4) {
        uint32_t queue = R32(0x006F7D8C + stream*4);
        LOGR("EA speech fetch: stream=%u channel=%u queue=%08X available=%u queuedSamples=%u", stream, channel, queue, unsigned(X86_MEM16(queue+0x34+channel*2)), R32(queue+0x48));
    }
    __imp__sub_00430010(ctx, base);
    if (tracing_codec4) LOGR("EA speech fetched: data=%08X length=%u flag=%08X", ctx.eax, R32(length), R32(flag));
}
X86_EXTERN_FUNC(__imp__sub_0043D648);
X86_FUNC(sub_0043D648) {
    uint32_t requested = kernel::R32(ctx.esp+8);
    __imp__sub_0043D648(ctx, base);
    if (tracing_codec4) LOGR("EA speech decode: requested=%u produced=%d", requested, int32_t(ctx.eax));
}

X86_EXTERN_FUNC(__imp__sub_00433091);
X86_FUNC(sub_00433091) {
    using kernel::R32;
    uint32_t channel = R32(ctx.esp + 4), codec = R32(ctx.esp + 8), mode = R32(ctx.esp + 12);
    int family = codec == 8 ? 0 : codec == 10 ? 1 : codec == 4 ? 2 : codec == 22 ? 3 : codec == 16 ? 4 : codec == 23 ? 5 : -1;
    int variant = mode == 0 ? 2 : mode == 1 && int32_t(R32(ctx.esp + 40)) > 0 ? 1 : 0;
    static std::atomic<unsigned> count{0};
    bool trace = count.fetch_add(1) < 100;
    if (trace) LOGR("EA decoder: channel=%u codec=%u mode=%u init=%08X input=%08X samples=%u", channel, codec, mode,
        family >= 0 ? R32(0x006F7E68 + 4 * (family * 3 + variant)) : 0,
        R32(ctx.esp + 16), R32(ctx.esp + 32));
    __imp__sub_00433091(ctx, base);
    if (codec == 4) speech_voice.store(R32(0x006F8030) + channel * 0x5C);
    if (trace) {
        uint32_t voice = R32(0x006F8030) + channel * 0x5C;
        LOGR("EA decoder ready: channel=%u chain=%08X decoder=%08X stream=%08X", channel, R32(voice + 0x40), R32(voice + 0x48), R32(voice + 0x4C));
    }
}

