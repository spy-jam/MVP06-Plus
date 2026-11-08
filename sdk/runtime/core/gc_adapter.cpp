// GameCube controller adapter (WUP-028) without SDL: SDL reaches this adapter only through libusb, which the
// runtime's static SDL is not built with, and an adapter given the WinUSB driver for Dolphin is not a HID device.
//
// Protocol (as Dolphin and SDL use it): write 0x13 to the OUT endpoint to start reports; each 37-byte IN report
// is 0x21 then four 9-byte ports: status (bits 4-5: 1 wired, 2 wireless; bit 2: rumble power), buttons
// (A B X Y left right down up), buttons (start Z R L), stick x y, C x y, L, R. Rumble is 0x11 and one byte per port.
#include "core/gc_adapter.h"

#ifndef _WIN32
// the SDK's Linux harness (sdk/harness) builds the runtime without Windows: no adapter there
namespace gcadapter {
void Start() {}
bool Read(int, input::GameCube&) { return false; }
void Rumble(int, bool) {}
}  // namespace gcadapter
#else

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <setupapi.h>
#include <winusb.h>
#include <hidsdi.h>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <memory>
#include <vector>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <cwctype>
#include <filesystem>
#include <mutex>
#include <string>
#include <thread>

#include "app/app.h"
#include "core/input.h"
#include "core/log.h"

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "winusb.lib")
#pragma comment(lib, "hid.lib")
#pragma comment(lib, "ws2_32.lib")

namespace gcadapter {

namespace {

constexpr wchar_t kIds[] = L"vid_057e&pid_0337";
constexpr UCHAR kEpIn = 0x81, kEpOut = 0x02;
// GUID_DEVINTERFACE_USB_DEVICE: every USB device has it, the WinUSB-bound adapter included
constexpr GUID kUsbDevice = {0xA5DCBF10, 0x6530, 0x11D2, {0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED}};

// Linux's hidraw node read on its own thread: a read there waits until a report comes, so a silent adapter would
// otherwise hold this loop forever. The thread has its own handle (Wine may not let a read and a write share one).
struct RawReader {
    HANDLE file = INVALID_HANDLE_VALUE;
    std::mutex m;
    std::condition_variable cv;
    std::deque<std::vector<uint8_t>> q;
    bool dead = false, abandoned = false;
    DWORD err = 0;
};

ULONGLONG g_bridge_heard = 0;  // last packet of any kind from gcbridge

struct Device {
    HANDLE file = INVALID_HANDLE_VALUE;
    WINUSB_INTERFACE_HANDLE usb = nullptr;  // null: the HID path
    DWORD in_len = 37, out_len = 5;          // HID report lengths, report id included
    const char* how = "";
    SOCKET sock = INVALID_SOCKET;  // the Linux bridge (gcbridge, under Proton): reports over UDP
    sockaddr_in bridge{};
    ULONGLONG hello_at = 0;
    std::shared_ptr<RawReader> raw;  // the hidraw path's reader
    bool hidraw = false;              // Linux hidraw: a 1-byte report goes as 00 + the byte (see OpenLinuxHidraw)
    bool started = false;             // the start report already sent and answered

    void Hello() {
        ULONGLONG t = GetTickCount64();
        if (t - hello_at < 1000) return;
        hello_at = t;
        sendto(sock, "GCB1", 4, 0, reinterpret_cast<const sockaddr*>(&bridge), sizeof(bridge));
    }
    bool Write(const uint8_t* data, DWORD n) {
        DWORD done = 0;
        if (sock != INVALID_SOCKET) {  // the bridge starts the adapter itself; rumble goes on to it
            if (n == 5 && data[0] == 0x11)
                sendto(sock, reinterpret_cast<const char*>(data), 5, 0, reinterpret_cast<const sockaddr*>(&bridge), sizeof(bridge));
            return true;
        }
        if (usb) return WinUsb_WritePipe(usb, kEpOut, const_cast<PUCHAR>(data), n, &done, nullptr) && done == n;
        if (hidraw && n == 1) {
            uint8_t two[2] = {0x00, data[0]};
            return WriteFile(file, two, 2, &done, nullptr) != 0;
        }
        uint8_t buf[64] = {};
        std::memcpy(buf, data, std::min<DWORD>(n, sizeof(buf)));
        return WriteFile(file, buf, std::min<DWORD>(std::max(out_len, n), sizeof(buf)), &done, nullptr) != 0;
    }
    int Read(uint8_t* buf, DWORD cap) {
        DWORD done = 0;
        if (sock != INVALID_SOCKET) {
            // reports as they are; the bridge's own lines (GCL1 + text) into this log; GCA1: it's alive
            ULONGLONG end = GetTickCount64() + 100;
            for (;;) {
                Hello();
                char pkt[600];
                int r = recv(sock, pkt, int(sizeof(pkt)), 0);
                if (r <= 0) return -1;
                g_bridge_heard = GetTickCount64();
                if (r >= 4 && !std::memcmp(pkt, "GCL1", 4)) LOGR("gcbridge: %.*s", r - 4, pkt + 4);
                else if (!(r == 4 && !std::memcmp(pkt, "GCA1", 4))) {
                    std::memcpy(buf, pkt, std::min<DWORD>(DWORD(r), cap));
                    return std::min<int>(r, int(cap));
                }
                if (GetTickCount64() >= end) {
                    SetLastError(WAIT_TIMEOUT);
                    return -1;
                }
            }
        }
        if (raw) {
            std::unique_lock lk(raw->m);
            if (!raw->cv.wait_for(lk, std::chrono::milliseconds(100), [&] { return !raw->q.empty() || raw->dead; })) {
                SetLastError(WAIT_TIMEOUT);
                return -1;
            }
            if (raw->q.empty()) {
                SetLastError(raw->err);
                return -1;
            }
            std::vector<uint8_t> v = std::move(raw->q.front());
            raw->q.pop_front();
            DWORD k = std::min<DWORD>(DWORD(v.size()), cap);
            std::memcpy(buf, v.data(), k);
            return int(k);
        }
        // exactly one report: the IN endpoint's packets are 37 bytes, its full packet size, so a longer read would run
        // on into the next report and leave every later read starting part way through one
        if (usb) return WinUsb_ReadPipe(usb, kEpIn, buf, std::min<DWORD>(cap, 37), &done, nullptr) ? int(done) : -1;
        return ReadFile(file, buf, std::min(cap, in_len), &done, nullptr) ? int(done) : -1;
    }
    void Close() {
        if (sock != INVALID_SOCKET) closesocket(sock);
        sock = INVALID_SOCKET;
        if (raw) {  // its thread closes its handle when its read comes back
            std::lock_guard lk(raw->m);
            raw->abandoned = true;
        }
        raw.reset();
        hidraw = false;
        if (usb) WinUsb_Free(usb);
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
        usb = nullptr;
        file = INVALID_HANDLE_VALUE;
    }
};

std::mutex g_lock;
uint8_t g_report[37] = {};
bool g_live = false;  // g_report is current
// a port counts as plugged in after 3 reports in a row say so, and as unplugged after 30 reports (about a quarter
// second) without it, so one odd report cannot plug or unplug a controller
bool g_plugged[4] = {};
int g_seen[4] = {}, g_missed[4] = {};
std::atomic<bool> g_rumble[4];
// each controller's resting values when it was plugged in, as the console's PAD origin
struct Origin {
    bool set = false;
    uint8_t sx, sy, cx, cy, l, r;
};
Origin g_origin[4];
// X, Y and Start held for 3 seconds: the console takes the sticks' and triggers' resting point again (the controller
// does it itself on a GameCube)
std::chrono::steady_clock::time_point g_recal_since[4];
bool g_recal_held[4] = {};

// device interface paths of a class whose hardware ids are the adapter's
int g_listed = 0;  // device interfaces seen in the last search, for the "none found" line

template <class F>
bool ForEachPath(const GUID& cls, F&& f) {
    HDEVINFO set = SetupDiGetClassDevsW(&cls, nullptr, nullptr, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (set == INVALID_HANDLE_VALUE) return false;
    bool found = false;
    SP_DEVICE_INTERFACE_DATA ifd{sizeof(ifd)};
    for (DWORD i = 0; !found && SetupDiEnumDeviceInterfaces(set, nullptr, &cls, i, &ifd); i++) {
        DWORD need = 0;
        SetupDiGetDeviceInterfaceDetailW(set, &ifd, nullptr, 0, &need, nullptr);
        if (!need) continue;
        std::string mem(need, '\0');
        auto* detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(mem.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);
        if (!SetupDiGetDeviceInterfaceDetailW(set, &ifd, detail, need, nullptr, nullptr)) continue;
        std::wstring path = detail->DevicePath;
        g_listed++;
        std::wstring lower = path;
        for (wchar_t& c : lower) c = wchar_t(std::towlower(c));
        if (lower.find(kIds) != std::wstring::npos) found = f(path);
    }
    SetupDiDestroyDeviceInfoList(set);
    return found;
}

bool OpenWinUsb(Device& d) {
    return ForEachPath(kUsbDevice, [&](const std::wstring& path) {
        HANDLE f = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                               OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED, nullptr);
        if (f == INVALID_HANDLE_VALUE) return false;
        WINUSB_INTERFACE_HANDLE h = nullptr;
        if (!WinUsb_Initialize(f, &h)) {  // the HID driver has it: the HID path below
            CloseHandle(f);
            return false;
        }
        ULONG ms = 1000;
        WinUsb_SetPipePolicy(h, kEpIn, PIPE_TRANSFER_TIMEOUT, sizeof(ms), &ms);
        WinUsb_SetPipePolicy(h, kEpOut, PIPE_TRANSFER_TIMEOUT, sizeof(ms), &ms);
        // some adapters only report after this class request (Dolphin and SDL send it too)
        WINUSB_SETUP_PACKET setup{0x21, 11, 0x0001, 0, 0};
        ULONG done = 0;
        WinUsb_ControlTransfer(h, setup, nullptr, 0, &done, nullptr);
        d.file = f;
        d.usb = h;
        d.how = "WinUSB";
        return true;
    });
}

bool OpenHid(Device& d) {
    GUID hid;
    HidD_GetHidGuid(&hid);
    return ForEachPath(hid, [&](const std::wstring& path) {
        HANDLE f = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                               OPEN_EXISTING, 0, nullptr);
        if (f == INVALID_HANDLE_VALUE) return false;
        PHIDP_PREPARSED_DATA pre = nullptr;
        HIDP_CAPS caps{};
        if (HidD_GetPreparsedData(f, &pre)) {
            HidP_GetCaps(pre, &caps);
            HidD_FreePreparsedData(pre);
        }
        if (caps.InputReportByteLength < 37) {  // another collection of the same device
            CloseHandle(f);
            return false;
        }
        d.file = f;
        d.usb = nullptr;
        d.in_len = caps.InputReportByteLength;
        d.out_len = caps.OutputReportByteLength ? caps.OutputReportByteLength : 5;
        d.how = "HID";
        return true;
    });
}

// Under Proton (SteamOS) Wine's HID layer finds the adapter but refuses the 1-byte start report (error 87: the
// report carries no data, which Wine's report parser has no entry for), so nothing ever comes. Wine opens Linux files
// through drive Z:, its hidraw node included: there the adapter takes the report as Dolphin sends it. The node is
// found by its HID id in sysfs; Linux hands one whole report per read, report id first, as the WinUSB path does.
bool UnderWine() {
    HMODULE nt = GetModuleHandleW(L"ntdll.dll");
    return nt && GetProcAddress(nt, "wine_get_version");
}

// The bridge: gcbridge beside the exe (a Linux program; tools/gcbridge) reads the adapter over USB as Dolphin does
// and sends its reports to 127.0.0.1:47337's caller, with its own log lines (into this log, "gcbridge:").
//
// Wine starts a Linux program by fork and exec and says "started" once the exec is under way, whatever happens to
// the program next, so it's started through /bin/sh: the shell marks it executable (no chmod by hand), and writes
// what happened, its output and its exit code included, to gcbridge.out beside it, which comes into this log if the
// bridge is never heard from.
std::string UnixPath(const std::filesystem::path& p) {
    using Fn = char*(__cdecl*)(LPCWSTR);
    static Fn fn = reinterpret_cast<Fn>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "wine_get_unix_file_name"));
    if (fn) {
        if (char* u = fn(p.wstring().c_str())) {
            std::string r(u);
            HeapFree(GetProcessHeap(), 0, u);
            return r;
        }
    }
    std::wstring w = p.wstring();  // Proton's Z: is /
    if (w.size() < 3 || (w[0] != L'Z' && w[0] != L'z') || w[1] != L':') return {};
    w = w.substr(2);
    for (wchar_t& c : w)
        if (c == L'\\') c = L'/';
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), int(w.size()), nullptr, 0, nullptr, nullptr);
    std::string r(size_t(n), '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), int(w.size()), r.data(), n, nullptr, nullptr);
    return r;
}

std::wstring Wide(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), int(s.size()), nullptr, 0);
    std::wstring w(size_t(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), int(s.size()), w.data(), n);
    return w;
}

// a Windows command-line argument (Wine splits the line into the Linux argv by Windows' rules)
std::wstring Quote(const std::wstring& a) {
    std::wstring r = L"\"";
    for (wchar_t c : a) {
        if (c == L'"') r += L'\\';
        r += c;
    }
    return r + L"\"";
}

// the file's lines into this log, prefixed with its name; false if it isn't there
bool LogFile(const std::filesystem::path& p, const char* name) {
    FILE* f = _wfopen(p.wstring().c_str(), L"r");
    if (!f) return false;
    char line[512];
    for (int i = 0; i < 60 && std::fgets(line, sizeof(line), f); i++) {
        line[std::strcspn(line, "\r\n")] = 0;
        LOGR("%s: %s", name, line);
    }
    std::fclose(f);
    return true;
}

bool OpenBridge(Device& d) {
    static ULONGLONG launched_at = 0;
    static bool told_start = false, checked = false;
    static int told_quiet = 0;
    static int silent_launches = 0;  // started and never heard from: after 3, not started again
    std::filesystem::path dir = app::ExeDir(), exe = dir / L"gcbridge", log = dir / L"gcbridge.log",
                          out = dir / L"gcbridge.out";
    std::error_code ec;
    if (!std::filesystem::is_regular_file(exe, ec)) return false;
    if (!checked) {  // this package's gcbridge, not one left from an older one
        checked = true;
        std::string bytes;
        if (FILE* f = _wfopen(exe.wstring().c_str(), L"rb")) {
            char b[65536];
            size_t n;
            while ((n = std::fread(b, 1, sizeof(b), f)) > 0 && bytes.size() < (16u << 20)) bytes.append(b, n);
            std::fclose(f);
        }
        if (bytes.find("GCBRIDGE-PROTOCOL-3") == std::string::npos)
            LOGR("gcadapter: the gcbridge beside the exe (%zu bytes) is not this version's: copy this package's "
                 "gcbridge over it", bytes.size());
    }
    static bool wsa = [] { WSADATA w; return WSAStartup(MAKEWORD(2, 2), &w) == 0; }();
    if (!wsa) return false;
    SOCKET s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s == INVALID_SOCKET) return false;
    sockaddr_in me{};
    me.sin_family = AF_INET;
    me.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    DWORD ms = 100;
    bind(s, reinterpret_cast<sockaddr*>(&me), sizeof(me));
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));
    d.sock = s;
    d.bridge.sin_family = AF_INET;
    d.bridge.sin_port = htons(47337);
    d.bridge.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    d.hello_at = 0;
    uint8_t buf[64];
    auto wait_report = [&](ULONGLONG total) {
        ULONGLONG end = GetTickCount64() + total;
        while (GetTickCount64() < end) {
            int n = d.Read(buf, sizeof(buf));
            if (n >= 37 && buf[0] == 0x21) return true;
        }
        return false;
    };
    auto ok = [&] {
        d.how = "gcbridge (Proton)";
        d.started = true;  // the bridge started the adapter itself
        return true;
    };
    if (wait_report(700)) return ok();  // one already running (this game's, or one from Steam's launch options)
    bool launched = false, via_sh = false;
    ULONGLONG t = GetTickCount64();
    if (silent_launches < 3 && t - g_bridge_heard > 3000 && (!launched_at || t - launched_at > 10000)) {
        launched_at = t;
        DeleteFileW(log.wstring().c_str());  // so what's there afterwards is this run's
        DeleteFileW(out.wstring().c_str());
        std::string unix_exe = UnixPath(exe);
        std::filesystem::path sh = L"Z:\\bin\\sh";
        STARTUPINFOW si{sizeof(si)};
        PROCESS_INFORMATION pi{};
        BOOL started = FALSE;
        if (!unix_exe.empty() && std::filesystem::exists(sh, ec)) {
            via_sh = true;
            std::wstring script =
                L"exec >\"$0.out\" 2>&1; echo \"sh ran: $0\"; ls -l \"$0\"; [ -x \"$0\" ] || chmod +x \"$0\"; "
                L"\"$0\"; echo \"gcbridge exited ($?)\"";
            std::wstring cmd = L"/bin/sh -c " + Quote(script) + L" " + Quote(Wide(unix_exe));
            started = CreateProcessW(sh.wstring().c_str(), cmd.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr,
                                     dir.wstring().c_str(), &si, &pi);
        }
        if (!started) {  // no shell to go through: the program itself (it must be executable then)
            via_sh = false;
            std::wstring cmd = Quote(exe.wstring());
            started = CreateProcessW(exe.wstring().c_str(), cmd.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                                     nullptr, dir.wstring().c_str(), &si, &pi);
        }
        if (started) {
            if (pi.hThread) CloseHandle(pi.hThread);  // (Wine hands back no handles for a Linux program)
            if (pi.hProcess) CloseHandle(pi.hProcess);
            if (!told_start) LOGR("gcadapter: started gcbridge (%s)", via_sh ? "through /bin/sh" : "directly");
            told_start = true;
            launched = true;
        } else {
            static bool told = false;
            if (!told)
                LOGR("gcadapter: gcbridge is there but wouldn't start (error %lu): mark it executable (chmod +x gcbridge)",
                     GetLastError());
            told = true;
            d.Close();
            return false;
        }
    }
    if (wait_report(4000)) return ok();
    if (GetTickCount64() - g_bridge_heard < 3000) {
        // it's running and has said why it has no adapter (its lines above); asked again in a moment
    } else if (launched && ++silent_launches == 3) {
        // (one started from Steam's launch options is still listened for, every second)
        LOGR("gcadapter: gcbridge started 3 times and never answered: not starting it again this session. Under "
             "Proton, start it from the game's Steam launch options (see the handoff)");
    }
    if (launched && GetTickCount64() - g_bridge_heard >= 3000 && told_quiet++ < 3) {
        // not a word from it: what the shell and its own log say
        LOGR("gcadapter: gcbridge said nothing over 127.0.0.1 in 4 s");
        bool any = LogFile(out, "gcbridge.out");
        any |= LogFile(log, "gcbridge.log");
        if (!any)
            LOGR("gcadapter: no gcbridge.out%s and no gcbridge.log: nothing ran. Put the full path of gcbridge, then "
                 "& %%command%%, in the game's Steam launch options (see the handoff)",
                 via_sh ? " from /bin/sh" : "");
    }
    d.Close();
    return false;
}

// Linux's hidraw node through drive Z:. hidraw takes no write under 2 bytes, but a write starting 00 is a report
// without an id: the kernel (usbhid_output_report) drops the 00 and sends the rest, so 00 13 reaches the adapter as
// the 13 alone, as Dolphin sends it (13 00 went as two bytes, which the adapter ignores). Rumble (11 + 4) goes as is.
bool OpenLinuxHidraw(Device& d) {
    static bool failed = false;  // took the start but sent nothing: the bridge from then on
    if (failed) return false;
    for (int i = 0; i < 64; i++) {
        wchar_t uevent[96];
        swprintf(uevent, 96, L"Z:\\sys\\class\\hidraw\\hidraw%d\\device\\uevent", i);
        HANDLE u = CreateFileW(uevent, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr);
        if (u == INVALID_HANDLE_VALUE) continue;
        char text[1024] = {};
        DWORD got = 0;
        ReadFile(u, text, sizeof(text) - 1, &got, nullptr);
        CloseHandle(u);
        std::string t(text, got);
        for (char& c : t) c = char(std::toupper(static_cast<unsigned char>(c)));
        if (t.find("HID_ID=0003:0000057E:00000337") == std::string::npos) continue;
        wchar_t node[48];
        swprintf(node, 48, L"Z:\\dev\\hidraw%d", i);
        auto open = [&] {
            return CreateFileW(node, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                               OPEN_EXISTING, 0, nullptr);
        };
        HANDLE w = open();
        HANDLE r = w == INVALID_HANDLE_VALUE ? w : open();
        if (r == INVALID_HANDLE_VALUE) {
            LOGR("gcadapter: the adapter is /dev/hidraw%d but it can't be opened (error %lu): it needs a udev rule "
                 "giving you access", i, GetLastError());
            if (w != INVALID_HANDLE_VALUE) CloseHandle(w);
            continue;
        }
        auto reader = std::make_shared<RawReader>();
        reader->file = r;
        std::thread([reader] {
            for (;;) {
                uint8_t b[64];
                DWORD n = 0;
                BOOL okr = ReadFile(reader->file, b, sizeof(b), &n, nullptr);
                std::lock_guard lk(reader->m);
                if (reader->abandoned) break;
                if (!okr) {
                    reader->dead = true;
                    reader->err = GetLastError();
                    reader->cv.notify_all();
                    break;
                }
                if (n && reader->q.size() < 64) reader->q.emplace_back(b, b + n);
                reader->cv.notify_all();
                if (!n) Sleep(1);
            }
            CloseHandle(reader->file);
        }).detach();
        d.file = w;
        d.usb = nullptr;
        d.raw = reader;
        d.hidraw = true;
        d.in_len = 64;
        d.out_len = 2;
        d.how = "Linux hidraw (Proton)";
        // started and answering within 2 seconds, or not this way
        const uint8_t start = 0x13;
        int odd_reads = 0;
        for (int attempt = 0; attempt < 2; attempt++) {
            if (!d.Write(&start, 1)) {
                LOGR("gcadapter: /dev/hidraw%d: the start report (00 13) was refused (error %lu)", i, GetLastError());
                break;
            }
            for (int k = 0; k < 10; k++) {
                uint8_t buf[64];
                int n = d.Read(buf, sizeof(buf));
                if (n >= 37 && buf[0] == 0x21) {
                    d.started = true;
                    return true;
                }
                if (n > 0 && odd_reads++ < 4) {
                    char hex[3 * 12 + 1] = {};
                    for (int b = 0; b < n && b < 12; b++) std::snprintf(hex + 3 * b, 4, "%02X ", buf[b]);
                    LOGR("gcadapter: /dev/hidraw%d sent %d bytes: %s", i, n, hex);
                }
                if (n < 0 && GetLastError() != WAIT_TIMEOUT && odd_reads++ < 4)
                    LOGR("gcadapter: /dev/hidraw%d read failed (error %lu)", i, GetLastError());
            }
        }
        LOGR("gcadapter: /dev/hidraw%d took the start report but sent no reports in 2 s (SDL and Dolphin don't use "
             "hidraw for this adapter either)", i);
        failed = true;
        d.Close();
        return false;
    }
    return false;
}

void Run() {
    bool told_missing = false;
    for (;;) {
        Device d;
        g_listed = 0;
        if (!OpenWinUsb(d) && !(UnderWine() && (OpenBridge(d) || OpenLinuxHidraw(d))) && !OpenHid(d)) {
            // under Proton (SteamOS) the adapter shows up only as a HID device, and only when Proton is told to pass
            // it through (PROTON_ENABLE_HIDRAW=0x057E/0x0337) and Steam isn't holding it for its own GameCube support
            if (!told_missing)
                LOGR("gcadapter: no GameCube adapter found (%d USB/HID interfaces listed, none 057E:0337), looking "
                     "again every second", g_listed);
            told_missing = true;
            std::this_thread::sleep_for(std::chrono::seconds(1));
            continue;
        }
        told_missing = false;
        const uint8_t start = 0x13;
        if (!d.started && !d.Write(&start, 1)) {
            static int told_start = 0;  // (Wine's HID route refuses it every time: said 3 times, not all session)
            if (told_start++ < 3)
                LOGR("gcadapter: adapter found (%s) but would not start (error %lu)%s", d.how, GetLastError(),
                     told_start == 3 ? "; not saying it again" : "");
            d.Close();
            std::this_thread::sleep_for(std::chrono::seconds(2));
            continue;
        }
        LOGR("gcadapter: GameCube adapter opened through %s", d.how);
        bool rumble_sent[4] = {};
        int logged = 0, odd = 0;
        int failures = 0;
        for (;;) {
            uint8_t buf[64];
            int n = d.Read(buf, sizeof(buf));
            // the first reads after opening, and any odd ones later, in the log (what the adapter sends, for Proton)
            if (logged < 6 || (n != 37 && odd < 20)) {
                if (logged >= 6) odd++;
                logged++;
                char hex[3 * 12 + 1] = {};
                for (int i = 0; i < n && i < 12; i++) std::snprintf(hex + 3 * i, 4, "%02X ", buf[i]);
                if (n < 0) LOGR("gcadapter: read failed (error %lu)", GetLastError());
                else LOGR("gcadapter: read %d bytes: %s", n, hex);
            }
            if (n < 0) {
                if (++failures < 5) continue;  // a timeout while idle is not a lost adapter
                break;
            }
            failures = 0;
            if (n >= 37 && buf[0] == 0x21) {
                std::lock_guard lock(g_lock);
                std::memcpy(g_report, buf, 37);
                g_live = true;
                for (int i = 0; i < 4; i++) {
                    bool on = (buf[1 + 9 * i] & 0x30) != 0;
                    g_seen[i] = on ? g_seen[i] + 1 : 0;
                    g_missed[i] = on ? 0 : g_missed[i] + 1;
                    if (g_seen[i] >= 3) g_plugged[i] = true;
                    if (g_missed[i] >= 30) g_plugged[i] = false;
                }
            }
            bool want[4];
            bool change = false;
            for (int i = 0; i < 4; i++) {
                want[i] = g_rumble[i].load();
                change |= want[i] != rumble_sent[i];
            }
            if (change) {
                uint8_t rumble[5] = {0x11, want[0], want[1], want[2], want[3]};
                if (d.Write(rumble, 5)) std::copy(want, want + 4, rumble_sent);
            }
        }
        LOGR("gcadapter: GameCube adapter lost (error %lu), reopening", GetLastError());
        d.Close();
        {
            std::lock_guard lock(g_lock);
            g_live = false;
            for (int i = 0; i < 4; i++) g_plugged[i] = false, g_seen[i] = g_missed[i] = 0;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
}

// What the GameCube release does with a PADRead: PADClampCircle (the SDK's padclamp.c), then the gcpad poll
// fn_8000A44C scales the result into the game's channels: control stick / 55, C stick / 43, triggers / 150.
// Doing the same here and scaling to the Xbox report's ranges (stick / 32768, triggers / 255) hands the Xbox
// build the very values the GameCube build worked with, so a full tilt runs at full speed as it did there.
void ClampCircle(int& x, int& y, int radius, int min) {
    auto dead = [&](int v) { return (-min < v && v < min) ? 0 : v > 0 ? v - min : v + min; };
    x = dead(x);
    y = dead(y);
    int squared = x * x + y * y;
    if (radius * radius < squared) {
        int length = int(std::sqrt(float(squared)));
        x = x * radius / length;
        y = y * radius / length;
    }
}

int ClampTrigger(int t, int min, int max) {
    if (t <= min) return 0;
    return std::min(t, max) - min;
}

int16_t Stick(int v, int full) { return int16_t(std::clamp(v * 32768 / full, -32767, 32767)); }

}  // namespace

void Start() {
    static std::once_flag once;
    std::call_once(once, [] { std::thread(Run).detach(); });
}

bool Read(int slot, input::GameCube& gc) {
    if (slot < 0 || slot > 3) return false;
    std::lock_guard lock(g_lock);
    const uint8_t* p = g_report + 1 + 9 * slot;
    Origin& o = g_origin[slot];
    if (!g_live || !g_plugged[slot]) {
        o.set = false;
        return false;
    }
    bool xys = (p[1] & 0x0C) == 0x0C && (p[2] & 0x01);  // X Y, Start
    auto now = std::chrono::steady_clock::now();
    if (!xys) {
        g_recal_held[slot] = false;
    } else if (!g_recal_held[slot]) {
        g_recal_held[slot] = true;
        g_recal_since[slot] = now;
    } else if (now - g_recal_since[slot] >= std::chrono::seconds(3)) {
        o.set = false;
        g_recal_since[slot] = now + std::chrono::hours(24);  // once per hold
        LOGR("gcadapter: port %d recentred (X + Y + Start)", slot + 1);
    }
    if (!o.set) o = {true, p[3], p[4], p[5], p[6], p[7], p[8]};
    using G = input::GameCube;
    constexpr uint16_t kLow[8] = {G::A, G::B, G::X, G::Y, G::Left, G::Right, G::Down, G::Up};
    constexpr uint16_t kHigh[4] = {G::Start, G::Z, G::RClick, G::LClick};
    gc = {};
    gc.present = true;
    for (int i = 0; i < 8; i++)
        if (p[1] & (1 << i)) gc.buttons |= kLow[i];
    for (int i = 0; i < 4; i++)
        if (p[2] & (1 << i)) gc.buttons |= kHigh[i];
    // PADRead's values: sticks centred on the controller's resting point (y up, as the report has it), triggers raw
    int sx = int(p[3]) - o.sx, sy = int(p[4]) - o.sy, cx = int(p[5]) - o.cx, cy = int(p[6]) - o.cy;
    ClampCircle(sx, sy, 56, 15);  // ClampRegion.radStick, minStick
    ClampCircle(cx, cy, 44, 15);  // radSubstick, minSubstick
    gc.lx = Stick(sx, 55);
    gc.ly = Stick(sy, 55);
    gc.cx = Stick(cx, 43);
    gc.cy = Stick(cy, 43);
    // triggers from rest, then ClampTrigger(30, 180): 0-150, which the game reads as 0-1
    int l = std::max(int(p[7]) - o.l, 0), r = std::max(int(p[8]) - o.r, 0);
    gc.l = uint8_t(std::min(ClampTrigger(l, 30, 180) * 255 / 150, 255));
    gc.r = uint8_t(std::min(ClampTrigger(r, 30, 180) * 255 / 150, 255));
    return true;
}

void Rumble(int slot, bool on) {
    if (slot >= 0 && slot < 4) g_rumble[slot] = on;
}

}  // namespace gcadapter

#endif  // _WIN32
