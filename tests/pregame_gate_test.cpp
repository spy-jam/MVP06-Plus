#include "../src/game/pregame_speech_gate.h"
#include <cassert>
#include <cstdio>
int main() {
    PregameSpeechGate g;
    assert(g.Hold(0,false));
    assert(g.Hold(500,false));
    assert(!g.Hold(900,true));
    assert(!g.Hold(950,false)); // narration ended: no artificial hold
    assert(g.Hold(2000,false)); // a gap resets for the next matchup
    for (uint64_t t=2500;t<12000;t+=500) assert(g.Hold(t,false));
    assert(!g.Hold(12000,false)); // strict ten-second deadline
    assert(!g.Hold(12500,false)); // stays released, no indefinite retry
    assert(g.Hold(14000,false));
    assert(!g.Hold(14001,true));
    puts("PASS: initial silence, real speech, completion, matchup reset, 10-second timeout");
}
