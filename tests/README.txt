Optional standalone regression test, from the x64 developer prompt:
clang++ tests/pregame_gate_test.cpp -o pregame_gate_test.exe
pregame_gate_test.exe
Checks initial silence, actual speech, completion, session reset and timeout.
Do not compile with NDEBUG; this test uses assert.
