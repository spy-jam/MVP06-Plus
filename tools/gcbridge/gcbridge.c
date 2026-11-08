/* gcbridge: the GameCube controller adapter (WUP-028, 057E:0337) for the recomp running under Proton (SteamOS).

   A Windows program under Wine can't reach the adapter the way it needs: Wine's HID layer and Linux's hidraw both
   refuse the adapter's 1-byte start report. This small Linux program talks to it the way Dolphin does, over USB
   (usbfs, no libraries), and hands its 37-byte reports to the game over UDP on 127.0.0.1 (Wine's sockets are
   Linux's). The game starts it by itself when it finds it beside the exe under Wine; it ends a few seconds after the
   game stops asking.

   Protocol, port 47337 on 127.0.0.1:
     game -> bridge  "GCB1"                 hello, about every second (the bridge answers there)
     game -> bridge  11 aa bb cc dd         rumble, as the adapter takes it
     bridge -> game  21 + 36 bytes          each adapter report as it arrives
     bridge -> game  "GCL1" + text          a line of this log (the game puts it in its own, "gcbridge: ...")
     bridge -> game  "GCA1"                 about every second: it's running (with or without an adapter)

   Build (static, so it runs in Steam's container; plain x86-64): cc -O2 -march=x86-64 -static -s -o gcbridge gcbridge.c
   Needs read/write access to the adapter's /dev/bus/usb node (the same as Dolphin: SteamOS has it). */
#include <dirent.h>
#include <grp.h>
#include <sys/stat.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/usbdevice_fs.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#define PORT 47337
/* the game reads the file for this, to tell an old gcbridge from this one */
const char gcbridge_version[] = "GCBRIDGE-PROTOCOL-3";

/* gcbridge.log beside it, and each line to the game too: what it found, for when the adapter doesn't come up */
static FILE *logf;
static double t0;
static double now(void);
static int sock = -1, have_game;
static struct sockaddr_in game;
static char backlog[48][300];  /* lines from before the game's first hello */
static int backlog_n;
static void say(const char *line) {
    char pkt[304] = "GCL1";
    size_t n = strlen(line);
    if (n > 299) n = 299;
    memcpy(pkt + 4, line, n);
    sendto(sock, pkt, 4 + n, 0, (struct sockaddr *)&game, sizeof game);
}
#define LOG(...) do { \
        char line_[300]; \
        snprintf(line_, sizeof line_, __VA_ARGS__); \
        if (logf) { fprintf(logf, "[%8.3f] %s\n", now() - t0, line_); fflush(logf); } \
        fprintf(stderr, "gcbridge: %s\n", line_); \
        if (have_game) say(line_); \
        else if (backlog_n < 48) strcpy(backlog[backlog_n++], line_); \
    } while (0)
static unsigned char EP_IN = 0x81, EP_OUT = 0x02;  /* the official adapter's; read from sysfs when it's there */

/* the interface's interrupt endpoints, from sysfs (ep_81: type "Interrupt", direction "in") */
static void find_endpoints(const char *dev) {
    char dir[300];
    snprintf(dir, sizeof dir, "/sys/bus/usb/devices/%s:1.0", dev);
    DIR *d = opendir(dir);
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (strncmp(e->d_name, "ep_", 3)) continue;
        char p[600], t[32] = {0}, w[32] = {0};
        snprintf(p, sizeof p, "%s/%s/type", dir, e->d_name);
        FILE *f = fopen(p, "r");
        if (f) { if (!fgets(t, sizeof t, f)) t[0] = 0; fclose(f); }
        snprintf(p, sizeof p, "%s/%s/direction", dir, e->d_name);
        f = fopen(p, "r");
        if (f) { if (!fgets(w, sizeof w, f)) w[0] = 0; fclose(f); }
        if (strncmp(t, "Interrupt", 9)) continue;
        unsigned char a = (unsigned char)strtol(e->d_name + 3, NULL, 16);
        if (!strncmp(w, "in", 2)) EP_IN = a;
        else if (!strncmp(w, "out", 3)) EP_OUT = a;
    }
    closedir(d);
}

double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static int read_hex(const char *dir, const char *name) {
    char p[512], b[32] = {0};
    snprintf(p, sizeof p, "/sys/bus/usb/devices/%s/%s", dir, name);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    if (!fgets(b, sizeof b, f)) b[0] = 0;
    fclose(f);
    return (int)strtol(b, NULL, 16);
}

static int read_dec(const char *dir, const char *name) {
    char p[512], b[32] = {0};
    snprintf(p, sizeof p, "/sys/bus/usb/devices/%s/%s", dir, name);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    if (!fgets(b, sizeof b, f)) b[0] = 0;
    fclose(f);
    return atoi(b);
}

static void close_adapter(int fd);

static int send_start(int fd) {
    unsigned char start = 0x13;
    struct usbdevfs_bulktransfer bt = {EP_OUT, 1, 1000, &start};
    return ioctl(fd, USBDEVFS_BULK, &bt);
}

/* who has the node open (when the claim is refused): pid and name */
static void holders(const char *node) {
    DIR *p = opendir("/proc");
    if (!p) return;
    struct dirent *e;
    int found = 0;
    while ((e = readdir(p))) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char dir[300];
        snprintf(dir, sizeof dir, "/proc/%s/fd", e->d_name);
        DIR *f = opendir(dir);
        if (!f) continue;
        struct dirent *x;
        while ((x = readdir(f))) {
            char l[600], t[300] = {0};
            snprintf(l, sizeof l, "%s/%s", dir, x->d_name);
            if (readlink(l, t, sizeof t - 1) > 0 && !strcmp(t, node)) {
                char c[300], name[64] = "?";
                snprintf(c, sizeof c, "/proc/%s/comm", e->d_name);
                FILE *cf = fopen(c, "r");
                if (cf) { if (fgets(name, sizeof name, cf)) name[strcspn(name, "\n")] = 0; fclose(cf); }
                if ((int)atoi(e->d_name) != (int)getpid()) { LOG("  pid %s (%s)", e->d_name, name); found++; }
                break;
            }
        }
        closedir(f);
    }
    closedir(p);
    if (!found) LOG("  none that this program can see (another container, or the kernel)");
}

/* the adapter's usbfs node, opened and claimed; -1 if none */
static int open_adapter(void) {
    DIR *d = opendir("/sys/bus/usb/devices");
    static int told, told_found;
    if (!d) { if (!told++) LOG("no /sys/bus/usb/devices: %s", strerror(errno)); return -1; }
    int seen = 0, match = 0;
    struct dirent *e;
    int fd = -1;
    while ((e = readdir(d)) && fd < 0) {
        if (e->d_name[0] == '.' || strchr(e->d_name, ':')) continue;
        seen++;
        if (read_hex(e->d_name, "idVendor") != 0x057e || read_hex(e->d_name, "idProduct") != 0x0337) continue;
        match++;
        char node[64];
        snprintf(node, sizeof node, "/dev/bus/usb/%03d/%03d", read_dec(e->d_name, "busnum"), read_dec(e->d_name, "devnum"));
        if (!told_found++) {
            char drv[512] = "(none)", p[512];
            snprintf(p, sizeof p, "/sys/bus/usb/devices/%s:1.0/driver", e->d_name);
            ssize_t k = readlink(p, drv, sizeof drv - 1);
            if (k > 0) { drv[k] = 0; char *b = strrchr(drv, '/'); if (b) memmove(drv, b + 1, strlen(b)); }
            find_endpoints(e->d_name);
            LOG("adapter at %s (%s), its driver now: %s, endpoints in %02x out %02x", e->d_name, node, drv, EP_IN, EP_OUT);
        }
        fd = open(node, O_RDWR);
        if (fd < 0) {
            int err = errno;
            struct stat st;
            if (told >= 3) continue;
            if (stat(node, &st) < 0) LOG("open %s: %s (no such node here: no /dev/bus/usb in this container?)", node, strerror(err));
            else {
                gid_t g[64];
                int ng = getgroups(64, g);
                char gl[400] = "";
                for (int i = 0; i < ng && strlen(gl) < 380; i++) snprintf(gl + strlen(gl), sizeof gl - strlen(gl), " %u", (unsigned)g[i]);
                LOG("open %s: %s (node mode %o owner %u group %u; this is uid %u, groups%s)", node, strerror(err),
                    (unsigned)(st.st_mode & 07777), (unsigned)st.st_uid, (unsigned)st.st_gid, (unsigned)getuid(), gl);
            }
            continue;
        }
        unsigned int ifno = 0;
        struct usbdevfs_disconnect_claim dcl;
        memset(&dcl, 0, sizeof dcl);  /* interface 0, any driver: the kernel's HID driver lets go and it's ours */
        if (ioctl(fd, USBDEVFS_DISCONNECT_CLAIM, &dcl) < 0) {
            int err = errno;
            struct usbdevfs_ioctl dc = {0, USBDEVFS_DISCONNECT, NULL};
            ioctl(fd, USBDEVFS_IOCTL, &dc);
            if (ioctl(fd, USBDEVFS_CLAIMINTERFACE, &ifno) < 0) {
                if (told < 3) {
                    LOG("claim %s: %s (and %s); the ones holding it:", node, strerror(errno), strerror(err));
                    holders(node);
                }
                close(fd); fd = -1; continue;
            }
        }
        /* some adapters only report after this class request (Dolphin and SDL send it too) */
        struct usbdevfs_ctrltransfer ct = {0x21, 11, 0x0001, 0, 0, 1000, NULL};
        ioctl(fd, USBDEVFS_CONTROL, &ct);
        if (send_start(fd) < 0) {
            if (told < 3) LOG("start report to %s: %s", node, strerror(errno));
            close_adapter(fd); fd = -1; continue;
        }
        LOG("adapter %s claimed and started", node);
    }
    closedir(d);
    if (fd < 0 && told < 3) { told++; LOG("%d USB devices, %d adapters (057e:0337), none opened", seen, match); }
    return fd;
}

static void close_adapter(int fd) {
    unsigned int ifno = 0;
    ioctl(fd, USBDEVFS_RELEASEINTERFACE, &ifno);
    struct usbdevfs_ioctl cn = {0, USBDEVFS_CONNECT, NULL};  /* the HID driver back */
    ioctl(fd, USBDEVFS_IOCTL, &cn);
    close(fd);
}

int main(void) {
    t0 = now();
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in me = {0};
    me.sin_family = AF_INET;
    me.sin_port = htons(PORT);
    me.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (s < 0 || bind(s, (struct sockaddr *)&me, sizeof me) < 0) {  /* one is running already: it has the log */
        fprintf(stderr, "gcbridge: port %d: %s (one is running already?)\n", PORT, strerror(errno));
        return 1;
    }
    sock = s;
    /* the log beside the program itself (Wine may not hand a Linux program the game's folder as its own) */
    char self[4096] = {0};
    ssize_t sl = readlink("/proc/self/exe", self, sizeof self - 32);
    if (sl > 0) {
        char *slash = strrchr(self, '/');
        if (slash) strcpy(slash + 1, "gcbridge.log");
        logf = fopen(self, "w");
    }
    if (!logf) logf = fopen("gcbridge.log", "w");
    if (!logf) logf = fopen("/tmp/gcbridge.log", "w");
    LOG("gcbridge running (pid %d, uid %u, log %s)", (int)getpid(), (unsigned)getuid(), sl > 0 ? self : "?");
    fcntl(s, F_SETFL, O_NONBLOCK);
    double last_hello = now(), last_alive = 0, opened_at = 0;
    int fd = -1, restarts = 0;
    double next_try = 0;
    long reports = 0;
    for (;;) {
        /* the game's hellos and rumble */
        unsigned char m[16];
        struct sockaddr_in from;
        socklen_t fl = sizeof from;
        ssize_t r;
        while ((r = recvfrom(s, m, sizeof m, 0, (struct sockaddr *)&from, &fl)) > 0) {
            if (r == 4 && !memcmp(m, "GCB1", 4)) {
                int first = !have_game;
                game = from; have_game = 1; last_hello = now();
                if (first) {
                    for (int i = 0; i < backlog_n; i++) say(backlog[i]);
                    LOG("the game said hello (port %d)", ntohs(from.sin_port));
                }
            }
            else if (r == 5 && m[0] == 0x11 && fd >= 0) {
                struct usbdevfs_bulktransfer bt = {EP_OUT, 5, 100, m};
                static int told_rumble;
                if (ioctl(fd, USBDEVFS_BULK, &bt) < 0 && told_rumble++ < 3) LOG("rumble: %s", strerror(errno));
            }
            fl = sizeof from;
        }
        /* the game gone (or never came): stop */
        if (now() - last_hello > (have_game ? 5.0 : 180.0)) break;
        if (have_game && now() - last_alive >= 1.0) {
            last_alive = now();
            sendto(s, "GCA1", 4, 0, (struct sockaddr *)&game, sizeof game);
        }
        if (fd < 0) {
            if (now() >= next_try) {
                fd = open_adapter();
                next_try = now() + 1.0;
                if (fd >= 0) { opened_at = now(); reports = 0; restarts = 0; }
            }
            if (fd < 0) { usleep(100000); continue; }
        }
        /* started but silent: the start again, now and then (Dolphin sends it once; some adapters want it twice) */
        if (!reports && now() - opened_at > 1.0 + restarts && restarts < 5) {
            restarts++;
            LOG("no report %d s after the start: sending it again (%s)", restarts,
                send_start(fd) < 0 ? strerror(errno) : "sent");
        }
        unsigned char rep[37];
        struct usbdevfs_bulktransfer bt = {EP_IN, sizeof rep, 50, rep};
        int n = ioctl(fd, USBDEVFS_BULK, &bt);
        if (n < 0) {
            if (errno == ETIMEDOUT) continue;
            if (errno == EPIPE) {  /* a stall: cleared, and on */
                unsigned int ep = EP_IN;
                ioctl(fd, USBDEVFS_CLEAR_HALT, &ep);
                continue;
            }
            LOG("adapter lost: %s", strerror(errno));
            close(fd); fd = -1;
            continue;
        }
        if (!reports++) LOG("first report: %d bytes, %02x (working)", n, rep[0]);
        if (have_game && n > 0 && sendto(s, rep, n, 0, (struct sockaddr *)&game, sizeof game) < 0 && reports < 5)
            LOG("send to the game: %s", strerror(errno));
        if (reports == 1000) LOG("1000 reports passed on");
    }
    LOG("no hello for a while: the game is gone, stopping");
    if (fd >= 0) close_adapter(fd);
    return 0;
}
