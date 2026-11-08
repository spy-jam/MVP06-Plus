#pragma once
#include <cstdint>

// MVP06's loading check can precede narration startup on fast host storage.
struct PregameSpeechGate {
    bool initialized = false, saw_active = false;
    uint64_t first_ms = 0, last_ms = 0;
    bool Hold(uint64_t now, bool active) {
        if (!initialized || now - last_ms > 1000) {
            initialized = true;
            saw_active = false;
            first_ms = now;
        }
        last_ms = now;
        if (active) saw_active = true;
        return !saw_active && now - first_ms < 10000;
    }
};
