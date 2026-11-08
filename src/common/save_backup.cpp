#include "save_backup.h"

#include <algorithm>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

#include "app/app.h"
#include "core/log.h"

namespace fs = std::filesystem;

namespace saves {

namespace {

std::string Text(const fs::path& p) {  // for the log, on every platform
    auto u8 = p.u8string();
    return std::string(u8.begin(), u8.end());
}

constexpr const char* kList = "backup-contents.txt";  // in each backup: what it holds, and the mark of ours

// every file under the drive with its size and time, sorted: two drives with the same list hold the same saves
std::string Contents(const fs::path& drive) {
    std::vector<std::string> lines;
    std::error_code ec;
    for (fs::recursive_directory_iterator it(drive, fs::directory_options::skip_permission_denied, ec), end;
         !ec && it != end; it.increment(ec)) {
        if (!it->is_regular_file(ec)) continue;
        auto rel = fs::relative(it->path(), drive, ec).generic_u8string();
        auto size = it->file_size(ec);
        auto time = it->last_write_time(ec).time_since_epoch().count();
        std::ostringstream line;
        line << std::string(rel.begin(), rel.end()) << '\t' << size << '\t' << time;
        lines.push_back(line.str());
    }
    std::sort(lines.begin(), lines.end());
    std::string out;
    for (auto& l : lines) out += l + '\n';
    return out;
}

std::string ReadAll(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    std::ostringstream s;
    s << f.rdbuf();
    return s.str();
}

// the backups made for this hard disk, oldest first: by when each was completed (its list is written last)
std::vector<fs::path> Ours(const fs::path& root, const std::wstring& prefix) {
    std::vector<std::pair<fs::file_time_type, fs::path>> found;
    std::error_code ec;
    for (fs::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
        if (!it->is_directory(ec)) continue;
        std::wstring name = it->path().filename().wstring();
        if (name.rfind(prefix, 0) != 0 || !fs::is_regular_file(it->path() / kList, ec)) continue;
        // hdd's backups are named by date alone, hdd2's "hdd2 <date>": a date starts with a digit
        if (prefix.empty() && (name.empty() || name[0] < L'0' || name[0] > L'9')) continue;
        found.emplace_back(fs::last_write_time(it->path() / kList, ec), it->path());
    }
    std::sort(found.begin(), found.end());
    std::vector<fs::path> out;
    for (auto& f : found) out.push_back(f.second);
    return out;
}

std::wstring Stamp() {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
#ifdef _WIN32
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    wchar_t buf[32];
    wcsftime(buf, 32, L"%Y-%m-%d %H-%M-%S", &tm);
    return buf;
}

}  // namespace

void Backup() {
    if (!g_keep) {
        LOGI("save backups: off (save_backups = 0)");
        return;
    }
    try {
        // the same hard disk folder main.cpp gives the game: hdd, or hdd2... for a second copy on this PC
        std::wstring hdd = app::Instance() > 1 ? L"hdd" + std::to_wstring(app::Instance()) : L"hdd";
        fs::path drive = app::ExeDir() / hdd / L"E";
        fs::path root = app::ExeDir() / L"save backups";
        std::wstring prefix = app::Instance() > 1 ? hdd + L" " : L"";
        std::error_code ec;
        if (!fs::is_directory(drive, ec) || fs::is_empty(drive, ec)) {
            LOGI("save backups: no saves yet");
            return;
        }
        std::string contents = Contents(drive);
        auto backups = Ours(root, prefix);
        if (!backups.empty() && ReadAll(backups.back() / kList) == contents) {
            LOGI("save backups: saves unchanged since %s", Text(backups.back().filename()).c_str());
        } else {
            fs::path dst = root / (prefix + Stamp());
            for (int n = 2; fs::exists(dst, ec); n++) dst = root / (prefix + Stamp() + L" (" + std::to_wstring(n) + L")");
            fs::create_directories(dst, ec);
            fs::copy(drive, dst / L"E", fs::copy_options::recursive, ec);
            if (ec) {
                LOGE("save backups: copying to %s failed: %s", Text(dst).c_str(), ec.message().c_str());
                fs::remove_all(dst, ec);  // a partial copy is no backup; without the list it would never be pruned
                return;
            }
            std::ofstream(dst / kList, std::ios::binary) << contents;  // written last: only a complete copy is ours
            LOGR("save backups: saves copied to %s", Text(dst).c_str());
            backups.push_back(dst);
        }
        while (backups.size() > g_keep) {
            fs::remove_all(backups.front(), ec);
            LOGI("save backups: removed the oldest, %s", Text(backups.front().filename()).c_str());
            backups.erase(backups.begin());
        }
    } catch (const std::exception& e) {
        LOGE("save backups: %s", e.what());
    }
}

}  // namespace saves
