"""What controllers Windows sees right now, for the Launcher's status line, with Windows' own device list (SetupAPI)
and XInput, so nothing is opened: the game can still have every controller to itself.

  GameCube adapter   USB 057E:0337, and which driver it has: the game needs WinUSB (Zadig), as Dolphin does
  PlayStation        Sony 054C: DualShock 3 (0268), DualShock 4 (05C4, 09CC), DualSense (0CE6), DualSense Edge (0DF2)
  Switch Pro         057E:2009
  Xbox and others    XInput slots in use
"""
import ctypes
import os
import re

ADAPTER = (0x057E, 0x0337)
PC_MODE_ADAPTERS = {(0x0079, 0x1846), (0x0079, 0x1843), (0x0079, 0x1844)}  # third-party adapters switched to "PC"
PADS = {(0x054C, 0x0268): "DualShock 3", (0x054C, 0x05C4): "DualShock 4", (0x054C, 0x09CC): "DualShock 4",
        (0x054C, 0x0CE6): "DualSense", (0x054C, 0x0DF2): "DualSense Edge", (0x057E, 0x2009): "Switch Pro Controller"}
_IDS = re.compile(r"VID[_&]?(?:0002)?([0-9A-F]{4}).*?PID[_&]?([0-9A-F]{4})", re.I)


def _devices():
    """[(hardware ids, service, problem code)] of the devices present."""
    from ctypes import wintypes
    sa = ctypes.WinDLL("setupapi")
    cm = ctypes.WinDLL("cfgmgr32")

    class DEVINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", ctypes.c_byte * 16), ("DevInst", wintypes.DWORD),
                    ("Reserved", ctypes.c_void_p)]

    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    sa.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DEVINFO)]
    sa.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DEVINFO), wintypes.DWORD,
                                                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                     ctypes.POINTER(wintypes.DWORD)]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    h = sa.SetupDiGetClassDevsW(None, None, None, 0x2 | 0x4)  # DIGCF_PRESENT | DIGCF_ALLCLASSES
    if not h or h == ctypes.c_void_p(-1).value:
        return []
    out = []
    try:
        i = 0
        while True:
            d = DEVINFO()
            d.cbSize = ctypes.sizeof(DEVINFO)
            if not sa.SetupDiEnumDeviceInfo(h, i, ctypes.byref(d)):
                break
            i += 1

            def prop(code):
                buf = ctypes.create_unicode_buffer(1024)
                if sa.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(d), code, None, buf, ctypes.sizeof(buf), None):
                    return ctypes.wstring_at(ctypes.addressof(buf), 1024).split("\0\0")[0].split("\0")
                return []

            ids = prop(1)  # SPDRP_HARDWAREID
            if not ids or not any("VID" in x.upper() for x in ids):
                continue
            service = (prop(4) or [""])[0]  # SPDRP_SERVICE
            status, problem = wintypes.ULONG(), wintypes.ULONG()
            cm.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), d.DevInst, 0)
            out.append((ids, service, problem.value))
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    return out


def _xinput_slots():
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            x = ctypes.WinDLL(dll)
            break
        except OSError:
            continue
    else:
        return 0
    state = ctypes.create_string_buffer(16)
    return sum(1 for i in range(4) if x.XInputGetState(i, state) == 0)


def status():
    """{"adapter": (level, text), "pads": [names], "xinput": n} or None off Windows. level: ok / warn / none."""
    if os.name != "nt":
        return None
    adapter = None
    pads = []
    for ids, service, problem in _devices():
        m = next((_IDS.search(x) for x in ids if _IDS.search(x)), None)
        if not m:
            continue
        vp = (int(m.group(1), 16), int(m.group(2), 16))
        usb = any(x.upper().startswith("USB\\") for x in ids)
        if vp == ADAPTER and usb:
            if problem:
                adapter = ("warn", "GameCube adapter: plugged in, but it has no working driver. Give it WinUSB "
                                   "with Zadig (see the README).")
            elif service.lower() == "winusb":
                adapter = ("ok", "GameCube adapter: ready (WinUSB driver)")
            elif adapter is None or adapter[0] != "ok":
                adapter = ("warn", f"GameCube adapter: plugged in, but with the {service or 'wrong'} driver. "
                                   f"Give it WinUSB with Zadig (see the README).")
        elif vp in PC_MODE_ADAPTERS and adapter is None:
            adapter = ("warn", "GameCube adapter: it's in PC mode. Set its switch to Wii U, then give it "
                               "WinUSB with Zadig.")
        elif vp in PADS and PADS[vp] not in pads:
            pads.append(PADS[vp])
    return {"adapter": adapter or ("none", "GameCube adapter: not plugged in"), "pads": pads,
            "xinput": _xinput_slots()}


def summary(s):
    """(adapter (level, text), controllers line)"""
    names = list(s["pads"])
    if s["xinput"]:
        names.append(f"{s['xinput']} Xbox-style" + (" controllers" if s["xinput"] > 1 else " controller"))
    line = "Other controllers: " + (", ".join(names) if names else "none connected")
    return s["adapter"], line
