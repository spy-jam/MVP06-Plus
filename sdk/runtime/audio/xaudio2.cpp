// mixer output through XAudio2
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <xaudio2.h>

#include <thread>
#include <chrono>
#include <vector>

#include "audio/audio.h"
#include "core/log.h"

namespace audio {

void StartOutput(std::function<void(float*, uint32_t)> render) {
    std::thread([render] {
        CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        IXAudio2* xa = nullptr;
        IXAudio2MasteringVoice* master = nullptr;
        IXAudio2SourceVoice* voice = nullptr;
        WAVEFORMATEX wf{};
        wf.wFormatTag = WAVE_FORMAT_IEEE_FLOAT;
        wf.nChannels = 2;
        wf.nSamplesPerSec = kRate;
        wf.wBitsPerSample = 32;
        wf.nBlockAlign = 8;
        wf.nAvgBytesPerSec = kRate * 8;
        HRESULT hr = XAudio2Create(&xa, 0, XAUDIO2_DEFAULT_PROCESSOR);
        const char* stage = "XAudio2Create";
        if (SUCCEEDED(hr)) { stage = "CreateMasteringVoice"; hr = xa->CreateMasteringVoice(&master); }
        if (SUCCEEDED(hr)) { stage = "CreateSourceVoice"; hr = xa->CreateSourceVoice(&voice, &wf); }
        if (FAILED(hr)) {
            LOGE("audio: %s failed HRESULT=%08lX; no sound", stage, static_cast<unsigned long>(hr));
            if (master) master->DestroyVoice();
            if (xa) xa->Release();
            // Guest playback clocks and completion callbacks must keep advancing
            // even when the host has no usable audio endpoint.
            LOGR("audio: timed silent output active");
            constexpr uint32_t frames = kRate / 100;
            std::vector<float> discard(frames * 2);
            auto deadline = std::chrono::steady_clock::now();
            for (;;) {
                deadline += std::chrono::milliseconds(10);
                std::this_thread::sleep_until(deadline);
                render(discard.data(), frames);
                // Do not burst through guest audio after a suspended host.
                auto now = std::chrono::steady_clock::now();
                if (now - deadline > std::chrono::milliseconds(100)) deadline = now;
            }
        }
        voice->Start();
        constexpr uint32_t kFrames = kRate / 100, kSlots = 4;
        std::vector<float> bufs(kSlots * kFrames * 2);
        for (uint32_t n = 0;;) {
            XAUDIO2_VOICE_STATE st;
            voice->GetState(&st, XAUDIO2_VOICE_NOSAMPLESPLAYED);
            if (st.BuffersQueued >= 3) {
                Sleep(2);
                continue;
            }
            float* b = &bufs[(n % kSlots) * kFrames * 2];
            render(b, kFrames);
            XAUDIO2_BUFFER xb{};
            xb.AudioBytes = kFrames * 8;
            xb.pAudioData = reinterpret_cast<const BYTE*>(b);
            voice->SubmitSourceBuffer(&xb);
            n++;  // only a submitted buffer takes a slot, XAudio2 still reads the queued ones
        }
    }).detach();
}

}  // namespace audio
