"""The Launcher moved around with a controller, while one of its windows is in front: Xbox-style ones through XInput
(Xbox pads, and others Steam or DS4Windows present as one), and GameCube controllers on the adapter through its
WinUSB driver, as the game reads them. The adapter is let go before the game starts (release()), and not taken
while the game runs: only one program can hold it.

  D-pad / left stick   up and down: the previous / next control (in a list: the previous / next row)
                       left and right: a list box's or number's value, else the previous / next control
  A                    press the button, tick the box, open a row
  B                    back: closes a dialog (Esc)
  LB / RB              the previous / next tab
  Start                Launch, on the Play tab
On a GameCube controller: A, B, Start, L / R as LB / RB, the d-pad or the control stick.
In Windows' own message boxes, A is Enter, B is Esc and the d-pad moves between their buttons.
"""
import ctypes
import os
import time

POLL_MS = 33
REPEAT_DELAY, REPEAT_EVERY = 0.40, 0.12  # held direction: first repeat, then every

UP, DOWN, LEFT, RIGHT, START, BACK = 0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020
LB, RB, A, B = 0x0100, 0x0200, 0x1000, 0x2000
STICK = 16000


class _State(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint32), ("buttons", ctypes.c_uint16), ("lt", ctypes.c_uint8),
                ("rt", ctypes.c_uint8), ("lx", ctypes.c_int16), ("ly", ctypes.c_int16), ("rx", ctypes.c_int16),
                ("ry", ctypes.c_int16)]


def _xinput():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return getattr(ctypes.windll, name).XInputGetState
        except (OSError, AttributeError):
            pass
    return None


def _ours_in_front():
    """The window in front, if it's one of this process's: (hwnd, is Windows' own dialog)."""
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    if not h:
        return None, False
    pid = ctypes.c_ulong()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value != os.getpid():
        return None, False
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(h, cls, 64)
    return h, cls.value == "#32770"


def _key(vk, shift=False):
    u = ctypes.windll.user32
    if shift:
        u.keybd_event(0x10, 0, 0, 0)
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, 2, 0)
    if shift:
        u.keybd_event(0x10, 0, 2, 0)


class _Setup(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("RequestType", ctypes.c_uint8), ("Request", ctypes.c_uint8), ("Value", ctypes.c_uint16),
                ("Index", ctypes.c_uint16), ("Length", ctypes.c_uint16)]


class GameCubeAdapter:
    """The adapter's 4 ports read in the background through WinUSB (the driver Zadig gives it); buttons() is them
    as XInput buttons and a stick. Nothing happens when it isn't there, has another driver, or the game has it."""
    USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
    IDS = "vid_057e&pid_0337"
    EP_IN, EP_OUT = 0x81, 0x02

    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self.state = (0, 0, 0)
        self.stop = threading.Event()
        self.hand_over = threading.Event()  # let go for the game: taken again once it has started and closed
        self.file = self.usb = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _paths(self):
        from ctypes import wintypes
        sa = ctypes.WinDLL("setupapi")
        guid = (ctypes.c_byte * 16)()
        ctypes.oledll.ole32.CLSIDFromString(self.USB_DEVICE, guid)

        class IFD(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", ctypes.c_byte * 16),
                        ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]
        sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        sa.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
        sa.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                   ctypes.POINTER(IFD)]
        sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(IFD), ctypes.c_void_p,
                                                        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        h = sa.SetupDiGetClassDevsW(guid, None, None, 0x2 | 0x10)  # DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        if not h or h == ctypes.c_void_p(-1).value:
            return []
        out = []
        try:
            i = 0
            while True:
                ifd = IFD()
                ifd.cbSize = ctypes.sizeof(IFD)
                if not sa.SetupDiEnumDeviceInterfaces(h, None, guid, i, ctypes.byref(ifd)):
                    break
                i += 1
                need = wintypes.DWORD()
                sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value + 8)
                ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6  # cbSize
                if sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(ifd), buf, need, None, None):
                    path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                    if self.IDS in path.lower():
                        out.append(path)
        finally:
            sa.SetupDiDestroyDeviceInfoList(h)
        return out

    def _open(self):
        from ctypes import wintypes
        k, wu = ctypes.windll.kernel32, ctypes.WinDLL("winusb", use_last_error=True)
        k.CreateFileW.restype = wintypes.HANDLE
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.HANDLE]
        wu.WinUsb_Initialize.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        wu.WinUsb_SetPipePolicy.argtypes = [ctypes.c_void_p, ctypes.c_uint8, wintypes.ULONG, wintypes.ULONG,
                                            ctypes.c_void_p]
        wu.WinUsb_ControlTransfer.argtypes = [ctypes.c_void_p, _Setup, ctypes.c_void_p, wintypes.ULONG,
                                              ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p]
        wu.WinUsb_WritePipe.argtypes = wu.WinUsb_ReadPipe.argtypes = [
            ctypes.c_void_p, ctypes.c_uint8, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG),
            ctypes.c_void_p]
        wu.WinUsb_Free.argtypes = [ctypes.c_void_p]
        self.k, self.wu = k, wu
        for path in self._paths():
            f = k.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000080, None)  # read/write, shared, overlapped
            if not f or f == wintypes.HANDLE(-1).value:
                continue
            h = ctypes.c_void_p()
            if not wu.WinUsb_Initialize(f, ctypes.byref(h)):  # another driver (HID): left alone
                k.CloseHandle(f)
                continue
            ms = wintypes.ULONG(500)
            for ep in (self.EP_IN, self.EP_OUT):
                wu.WinUsb_SetPipePolicy(h, ep, 0x03, 4, ctypes.byref(ms))  # PIPE_TRANSFER_TIMEOUT
            done = wintypes.ULONG()
            wu.WinUsb_ControlTransfer(h, _Setup(0x21, 11, 1, 0, 0), None, 0, ctypes.byref(done), None)
            start = (ctypes.c_uint8 * 1)(0x13)
            wu.WinUsb_WritePipe(h, self.EP_OUT, start, 1, ctypes.byref(done), None)
            self.file, self.usb = f, h
            return True
        return False

    def _close(self):
        if self.usb:
            self.wu.WinUsb_Free(self.usb)
        if self.file:
            self.k.CloseHandle(self.file)
        self.file = self.usb = None
        with self.lock:
            self.state = (0, 0, 0)

    def _run(self):
        from ctypes import wintypes
        buf = (ctypes.c_uint8 * 37)()
        import time as _t
        held_until = 0.0
        while not self.stop.is_set():
            if self.hand_over.is_set():
                self._close()
                self.hand_over.clear()
                held_until = _t.monotonic() + 20  # the game's start: not taken back before it can open it
            if not self.usb:
                try:
                    import updater
                    if _t.monotonic() < held_until or updater.game_running() or not self._open():
                        self.stop.wait(3)
                        continue
                except Exception:
                    self.stop.wait(3)
                    continue
            n = wintypes.ULONG()
            if not self.wu.WinUsb_ReadPipe(self.usb, self.EP_IN, buf, 37, ctypes.byref(n), None):
                if ctypes.get_last_error() != 121:  # not a timeout (ERROR_SEM_TIMEOUT): unplugged
                    self._close()
                continue
            if n.value < 37 or buf[0] != 0x21:
                continue
            b, lx, ly = 0, 0, 0
            for port in range(4):
                p = buf[1 + port * 9: 10 + port * 9]
                if not (p[0] >> 4) & 3:  # nothing in this port
                    continue
                b1, b2 = p[1], p[2]
                for bit, x in ((0x01, A), (0x02, B), (0x10, LEFT), (0x20, RIGHT), (0x40, DOWN), (0x80, UP)):
                    if b1 & bit:
                        b |= x
                for bit, x in ((0x01, START), (0x08, LB), (0x04, RB)):
                    if b2 & bit:
                        b |= x
                sx, sy = (p[3] - 128) * 256, (p[4] - 128) * 256
                if abs(sx) > abs(lx):
                    lx = sx
                if abs(sy) > abs(ly):
                    ly = sy
            with self.lock:
                self.state = (b, lx, ly)
        self._close()

    def buttons(self):
        with self.lock:
            return self.state

    def release(self):
        """Let go of the adapter before the game starts; it's taken again only after the game has closed."""
        self.hand_over.set()
        for _ in range(40):  # the reader notices within a read's timeout (0.5 s)
            if not self.usb:
                return
            time.sleep(0.05)


_gc = None


def release():
    """Before starting the game: the GameCube adapter let go, so the game can open it."""
    if _gc:
        _gc.release()


def attach(w, tabs, on_start=None):
    """Polls the controllers while the Launcher runs; tabs: the main Notebook; on_start: Launch, when it can."""
    if os.name != "nt":
        return
    get = _xinput()
    global _gc
    try:
        _gc = GameCubeAdapter()
    except Exception:
        _gc = None
    if not get and not _gc:
        return
    import tkinter as tk
    from tkinter import ttk
    st = _State()
    last = {"buttons": 0, "dir": 0, "next": 0.0}

    def widget_class(wd):
        try:
            return wd.winfo_class()
        except tk.TclError:
            return ""

    def move_focus(forward):
        wd = w.focus_get()
        if wd is None:
            wd = tabs
        nxt = wd.tk_focusNext() if forward else wd.tk_focusPrev()
        if nxt is not None:
            nxt.focus_set()

    def change_value(wd, step):
        c = widget_class(wd)
        if c == "TCombobox":
            vals = list(wd.cget("values"))
            if vals:
                i = vals.index(wd.get()) if wd.get() in vals else -1
                wd.set(vals[max(0, min(len(vals) - 1, i + step))])
                wd.event_generate("<<ComboboxSelected>>")
            return True
        if c in ("TSpinbox", "Spinbox"):
            wd.invoke("buttonup" if step > 0 else "buttondown")
            return True
        return False

    def tree_move(wd, step):
        items = []

        def walk(parent):
            for it in wd.get_children(parent):
                items.append(it)
                if wd.item(it, "open"):
                    walk(it)
        walk("")
        if not items:
            return
        sel = wd.selection()
        i = items.index(sel[0]) if sel and sel[0] in items else -1
        it = items[max(0, min(len(items) - 1, i + step))]
        wd.selection_set(it)
        wd.focus(it)
        wd.see(it)

    def direction(d):
        h, native = _ours_in_front()
        if not h:
            return
        if native:
            _key(0x09, shift=d in (UP, LEFT))  # Tab / Shift+Tab between the dialog's buttons
            return
        wd = w.focus_get()
        c = widget_class(wd) if wd else ""
        if c == "Treeview" and d in (UP, DOWN):
            tree_move(wd, -1 if d == UP else 1)
        elif d in (LEFT, RIGHT) and wd is not None and change_value(wd, -1 if d == LEFT else 1):
            pass
        else:
            move_focus(d in (DOWN, RIGHT))

    def press(b):
        h, native = _ours_in_front()
        if not h:
            return
        if native:
            if b == A:
                _key(0x0D)
            elif b == B:
                _key(0x1B)
            return
        wd = w.focus_get()
        c = widget_class(wd) if wd else ""
        if b == A and wd is not None:
            if c in ("TButton", "Button", "TCheckbutton", "Checkbutton", "TRadiobutton"):
                wd.invoke()
            elif c == "Treeview":
                sel = wd.selection()
                if sel and wd.get_children(sel[0]):
                    wd.item(sel[0], open=not wd.item(sel[0], "open"))
                elif sel:
                    wd.event_generate("<Double-1>")
            elif c == "TCombobox":
                change_value(wd, 1)
            elif c == "TNotebook":
                move_focus(True)
        elif b == B:
            top = wd.winfo_toplevel() if wd is not None else w
            if top is not w:
                top.destroy()
        elif b in (LB, RB):
            n = len(tabs.tabs())
            if n:
                i = tabs.index(tabs.select())
                tabs.select((i + (1 if b == RB else -1)) % n)
                tabs.focus_set()
        elif b == START and on_start:
            on_start()

    def poll():
        buttons = 0
        lx = ly = 0
        if _gc:
            gb, gx, gy = _gc.buttons()
            buttons, lx, ly = gb, gx, gy
        for port in range(4 if get else 0):
            if get(port, ctypes.byref(st)) == 0:
                buttons |= st.buttons
                if abs(st.lx) > abs(lx):
                    lx = st.lx
                if abs(st.ly) > abs(ly):
                    ly = st.ly
        d = 0
        if buttons & UP or ly > STICK:
            d = UP
        elif buttons & DOWN or ly < -STICK:
            d = DOWN
        elif buttons & LEFT or lx < -STICK:
            d = LEFT
        elif buttons & RIGHT or lx > STICK:
            d = RIGHT
        now = time.monotonic()
        try:
            if d and (d != last["dir"] or now >= last["next"]):
                direction(d)
                last["next"] = now + (REPEAT_DELAY if d != last["dir"] else REPEAT_EVERY)
            last["dir"] = d
            pressed = buttons & ~last["buttons"]
            for b in (A, B, LB, RB, START):
                if pressed & b:
                    press(b)
        except tk.TclError:
            pass  # a window closed under it
        last["buttons"] = buttons
        try:
            w.after(POLL_MS, poll)
        except tk.TclError:
            pass

    w.after(POLL_MS, poll)
