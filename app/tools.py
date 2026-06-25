"""
Tools the assistant can call: local desktop actions + online APIs.
Risky actions go through CONFIRM_FN (set by the UI to a Yes/No dialog).
Every call is written to the audit log.
"""
import os
import re
import glob
import shutil
import fnmatch
import ctypes
import subprocess
import webbrowser
from ctypes import windll, byref, c_wchar_p
from uuid import UUID
from datetime import datetime
from urllib.parse import quote_plus

import requests

from . import config

MAX_READ_CHARS = 6000


# ---------- confirmation + audit (CONFIRM_FN replaced by the UI) ----------
def _console_confirm(description):
    ans = input(f"[CONFIRM] {description}\nType 'yes': ").strip().lower()
    return ans == "yes"

CONFIRM_FN = _console_confirm


def _audit(entry):
    try:
        with open(config.AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}  {entry}\n")
    except Exception:
        pass


def _confirm(description):
    ok = False
    try:
        ok = CONFIRM_FN(description)
    except Exception:
        ok = False
    _audit(f"CONFIRM {'GRANTED' if ok else 'DENIED'}: {description}")
    return ok


def _run_ps(command, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


# ---------- known folders (handles OneDrive redirection) ----------
class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort),
                ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


def _known_folder(guid_str):
    u = UUID(guid_str)
    g = _GUID()
    ctypes.memmove(byref(g), u.bytes_le, 16)
    p = c_wchar_p()
    if windll.shell32.SHGetKnownFolderPath(byref(g), 0, 0, byref(p)) != 0:
        return None
    val = p.value
    windll.ole32.CoTaskMemFree(p)
    return val


FOLDERS = {}
for _n, _g in {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}.items():
    try:
        FOLDERS[_n] = _known_folder(_g)
    except Exception:
        FOLDERS[_n] = None
FOLDERS["home"] = os.environ.get("USERPROFILE")


def _expand(p):
    return os.path.expandvars(os.path.expanduser(str(p)))


# ===================== ONLINE tools =====================
def web_search(query, max_results=5):
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            res = list(ddgs.text(str(query), max_results=int(max_results)))
        if not res:
            return f"No results for '{query}'."
        lines = [f"- {r.get('title','')}: {r.get('body','')} ({r.get('href','')})" for r in res]
        return f"Top web results for '{query}':\n" + "\n".join(lines)
    except Exception as e:
        return f"Web search failed: {e}"


def read_webpage(url):
    try:
        r = requests.get(str(url), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return f"Content of {url}:\n{text[:MAX_READ_CHARS]}" + (" ...(truncated)" if len(text) > MAX_READ_CHARS else "")
    except Exception as e:
        return f"Could not read {url}: {e}"


def get_weather(location):
    try:
        loc = quote_plus(str(location))
        r = requests.get(f"https://wttr.in/{loc}?format=%l:+%C,+%t+(feels+%f),+humidity+%h,+wind+%w",
                         timeout=15, headers={"User-Agent": "curl/8"})
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        return f"Could not get weather: {e}"


def open_url(url):
    u = str(url)
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    webbrowser.open(u)
    return f"Opened {u} in the browser."


def search_web_in_browser(query):
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(str(query))}")
    return f"Opened a browser search for: {query}"


# ===================== APP / WINDOW tools =====================
APP_ALIASES = {
    "calculator": "calc", "calc": "calc", "notepad": "notepad", "wordpad": "write",
    "paint": "mspaint", "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "microsoft edge": "msedge", "browser": "msedge", "firefox": "firefox",
    "explorer": "explorer", "file explorer": "explorer", "files": "explorer",
    "cmd": "cmd", "command prompt": "cmd", "powershell": "powershell",
    "terminal": "wt", "task manager": "taskmgr", "settings": "ms-settings:",
    "control panel": "control", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook", "spotify": "spotify", "vlc": "vlc",
}
CLOSE_ALIASES = {
    "calculator": ["CalculatorApp", "Calculator"], "notepad": ["notepad"], "paint": ["mspaint"],
    "chrome": ["chrome"], "google chrome": ["chrome"], "edge": ["msedge"], "microsoft edge": ["msedge"],
    "firefox": ["firefox"], "word": ["winword"], "excel": ["excel"], "powerpoint": ["powerpnt"],
    "outlook": ["outlook"], "spotify": ["Spotify"], "vlc": ["vlc"], "task manager": ["taskmgr"],
}


def open_app(name):
    raw = str(name).strip()
    target = APP_ALIASES.get(raw.lower(), raw).replace("'", "''")
    rc, _, _ = _run_ps(f"Start-Process '{target}'")
    return f"Opened '{name}'." if rc == 0 else f"Could not open '{name}'."


def close_app(name):
    raw = str(name).strip().lower()
    procs = CLOSE_ALIASES.get(raw, [raw.replace(".exe", "")])
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in procs)
    cmd = (f"$n=@({quoted}); $p=Get-Process -Name $n -ErrorAction SilentlyContinue;"
           "if(-not $p){'notfound'} else { $p|ForEach-Object{$_.CloseMainWindow()|Out-Null};"
           " Start-Sleep -Milliseconds 1200; $q=Get-Process -Name $n -ErrorAction SilentlyContinue;"
           " if($q){$q|Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 400};"
           " $r=Get-Process -Name $n -ErrorAction SilentlyContinue; if($r){'stillopen'} else {'closed'} }")
    rc, out, _ = _run_ps(cmd, timeout=20)
    if "closed" in out:
        return f"Closed '{name}'."
    if "notfound" in out:
        return f"'{name}' was not running."
    return f"Could not close '{name}'."


def manage_window(action, title=""):
    import pygetwindow as gw
    act = str(action).strip().lower()
    if act == "list":
        titles = list(dict.fromkeys(t for t in gw.getAllTitles() if t.strip()))
        return "Open windows: " + "; ".join(titles[:30]) if titles else "No visible windows."
    wins = gw.getWindowsWithTitle(title) or [w for w in gw.getAllWindows()
                                             if title and title.lower() in (w.title or "").lower()]
    if not wins:
        return f"No window matching '{title}'."
    w = wins[0]
    try:
        if act in ("focus", "activate", "show"):
            if w.isMinimized:
                w.restore()
            w.activate()
            return f"Focused: {w.title}"
        if act == "minimize":
            w.minimize(); return f"Minimized: {w.title}"
        if act == "maximize":
            w.maximize(); return f"Maximized: {w.title}"
        return f"Unknown window action: {action}."
    except Exception as e:
        return f"Could not {act} '{title}': {e}"


# ===================== FILE tools =====================
def get_special_folder(name):
    return FOLDERS.get(str(name).strip().lower()) or f"Unknown folder '{name}'. Known: {', '.join(FOLDERS)}"


def list_directory(path):
    path = _expand(path)
    if not os.path.isdir(path):
        return f"Not a folder: {path}"
    items = sorted(os.listdir(path))
    return f"{len(items)} items in {path}: " + ", ".join(items[:60]) + (" ..." if len(items) > 60 else "")


def read_file(path):
    path = _expand(path)
    if not os.path.isfile(path):
        return f"File not found: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(MAX_READ_CHARS + 1)
        return f"Contents of {path}:\n{data[:MAX_READ_CHARS]}" + (" ...(truncated)" if len(data) > MAX_READ_CHARS else "")
    except Exception as e:
        return f"Could not read {path}: {e}"


def write_file(path, content):
    path = _expand(path)
    verb = "OVERWRITE existing file" if os.path.isfile(path) else "create new file"
    if not _confirm(f"{verb}: {path}  ({len(content)} chars)"):
        return "Cancelled; nothing written."
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} characters to {path}."
    except Exception as e:
        return f"Could not write {path}: {e}"


def delete_file(path):
    path = _expand(path)
    if not os.path.isfile(path):
        return f"File does not exist: {path}"
    if not _confirm(f"DELETE file: {path}"):
        return "Cancelled; not deleted."
    try:
        os.remove(path); return f"Deleted {path}."
    except Exception as e:
        return f"Could not delete {path}: {e}"


def delete_files(folder, pattern):
    folder = _expand(folder)
    if not os.path.isdir(folder):
        return f"Not a folder: {folder}"
    matches = [f for f in os.listdir(folder)
               if os.path.isfile(os.path.join(folder, f)) and fnmatch.fnmatch(f.lower(), str(pattern).lower())]
    if not matches:
        return f"No files matching '{pattern}' in {folder}."
    if not _confirm(f"DELETE {len(matches)} file(s) matching '{pattern}' in {folder}:\n{', '.join(matches)}"):
        return "Cancelled; nothing deleted."
    deleted = []
    for m in matches:
        try:
            os.remove(os.path.join(folder, m)); deleted.append(m)
        except Exception:
            pass
    return f"Deleted {len(deleted)} file(s): {', '.join(deleted)}."


def create_folder(path):
    path = _expand(path)
    try:
        os.makedirs(path, exist_ok=True); return f"Folder ready: {path}"
    except Exception as e:
        return f"Could not create folder: {e}"


def copy_path(source, destination):
    s, d = _expand(source), _expand(destination)
    if not os.path.exists(s):
        return f"Source not found: {s}"
    if os.path.exists(d) and not _confirm(f"OVERWRITE {d} with a copy of {s}?"):
        return "Cancelled."
    try:
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
            shutil.copy2(s, d)
        return f"Copied to {d}."
    except Exception as e:
        return f"Could not copy: {e}"


def move_path(source, destination):
    s, d = _expand(source), _expand(destination)
    if not os.path.exists(s):
        return f"Source not found: {s}"
    if not _confirm(f"MOVE\n{s}\n-> {d}"):
        return "Cancelled."
    try:
        shutil.move(s, d); return f"Moved to {d}."
    except Exception as e:
        return f"Could not move: {e}"


def rename_path(path, new_name):
    p = _expand(path)
    if not os.path.exists(p):
        return f"Not found: {p}"
    d = os.path.join(os.path.dirname(p), str(new_name))
    if not _confirm(f"RENAME\n{p}\n-> {d}"):
        return "Cancelled."
    try:
        os.rename(p, d); return f"Renamed to {d}."
    except Exception as e:
        return f"Could not rename: {e}"


def search_files(folder, pattern, recursive=True):
    folder = _expand(folder)
    if not os.path.isdir(folder):
        return f"Not a folder: {folder}"
    pat = os.path.join(folder, "**", str(pattern)) if recursive else os.path.join(folder, str(pattern))
    hits = [h for h in glob.glob(pat, recursive=bool(recursive)) if os.path.isfile(h)]
    if not hits:
        return f"No files matching '{pattern}' under {folder}."
    return f"Found {len(hits)} file(s):\n" + "\n".join(hits[:40]) + (" ...(more)" if len(hits) > 40 else "")


# ===================== SYSTEM tools =====================
def set_volume(percent):
    try:
        from comtypes import CoInitialize
        from pycaw.pycaw import AudioUtilities
        CoInitialize()
        ep = AudioUtilities.GetSpeakers().EndpointVolume
        p = max(0, min(100, int(percent)))
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(p / 100.0, None)
        return f"Volume set to {p}%."
    except Exception as e:
        return f"Could not set volume: {e}"


_MEDIA = {"playpause": "play/pause media", "play": "play/pause media", "pause": "play/pause media",
          "next": "next track", "previous": "previous track", "prev": "previous track",
          "stop": "stop media", "volume_up": "volume up", "volume_down": "volume down", "mute": "volume mute"}


def media_control(action):
    import keyboard
    key = _MEDIA.get(str(action).lower().replace(" ", "_"))
    if not key:
        return f"Unknown media action: {action}."
    keyboard.send(key)
    return f"Sent media command: {action}."


def set_brightness(percent):
    p = max(0, min(100, int(percent)))
    rc, _, err = _run_ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{p})")
    return f"Brightness set to {p}%." if rc == 0 else f"Could not set brightness: {err}"


def power_control(action):
    a = str(action).strip().lower()
    if a == "lock":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"]); return "Screen locked."
    if a in ("sleep", "suspend"):
        if not _confirm("Put the computer to SLEEP now?"):
            return "Cancelled."
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]); return "Going to sleep."
    if a == "restart":
        if not _confirm("RESTART the computer now?"):
            return "Cancelled."
        subprocess.run(["shutdown", "/r", "/t", "5"]); return "Restarting in 5 seconds."
    if a == "shutdown":
        if not _confirm("SHUT DOWN the computer now?"):
            return "Cancelled."
        subprocess.run(["shutdown", "/s", "/t", "5"]); return "Shutting down in 5 seconds."
    return f"Unknown power action: {action}."


def get_battery():
    try:
        rc, out, _ = _run_ps("(Get-CimInstance Win32_Battery).EstimatedChargeRemaining")
        return f"Battery is at {out.splitlines()[0].strip()}%." if out else "No battery detected."
    except Exception as e:
        return f"Could not read battery: {e}"


def get_system_info():
    cmd = ("$o=Get-CimInstance Win32_OperatingSystem;$c=Get-CimInstance Win32_ComputerSystem;"
           "'{0}; RAM {1:N0} GB; free {2:N0} GB' -f $o.Caption,($c.TotalPhysicalMemory/1GB),($o.FreePhysicalMemory/1MB/1024)")
    rc, out, _ = _run_ps(cmd)
    return out or "Could not read system info."


def run_powershell(command):
    command = str(command)
    if not _confirm(f"Run PowerShell command:\n{command}"):
        return "Cancelled; command not run."
    try:
        rc, out, err = _run_ps(command, timeout=60)
        result = out if out else "(no output)"
        if err:
            result += f"\n[stderr] {err}"
        return result[:MAX_READ_CHARS]
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Error: {e}"


def get_datetime():
    return datetime.now().strftime("It is %A, %d %B %Y, %I:%M %p.")


# ===================== registry + schemas =====================
FUNCS = {
    # online
    "web_search": web_search, "read_webpage": read_webpage, "get_weather": get_weather,
    "open_url": open_url, "search_web_in_browser": search_web_in_browser,
    # apps / windows
    "open_app": open_app, "close_app": close_app, "manage_window": manage_window,
    # files
    "get_special_folder": get_special_folder, "list_directory": list_directory,
    "read_file": read_file, "write_file": write_file, "delete_file": delete_file,
    "delete_files": delete_files, "create_folder": create_folder, "copy_path": copy_path,
    "move_path": move_path, "rename_path": rename_path, "search_files": search_files,
    # system
    "set_volume": set_volume, "media_control": media_control, "set_brightness": set_brightness,
    "power_control": power_control, "get_battery": get_battery, "get_system_info": get_system_info,
    "run_powershell": run_powershell, "get_datetime": get_datetime,
}


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}

TOOL_SCHEMAS = [
    _fn("web_search", "Search the web and return result snippets. Use for current/factual info you don't know.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("read_webpage", "Fetch a web page and return its text (to read or summarize it).",
        {"url": {"type": "string"}}, ["url"]),
    _fn("get_weather", "Get the current weather for a city/location.",
        {"location": {"type": "string"}}, ["location"]),
    _fn("open_url", "Open a URL in the default browser.", {"url": {"type": "string"}}, ["url"]),
    _fn("search_web_in_browser", "Open a browser window with a search for the query.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("open_app", "Open/launch an application by name (Calculator, Notepad, Chrome, Settings...).",
        {"name": {"type": "string"}}, ["name"]),
    _fn("close_app", "Close/quit a running application by name.", {"name": {"type": "string"}}, ["name"]),
    _fn("manage_window", "Focus, minimize, maximize, or list application windows.",
        {"action": {"type": "string", "description": "focus|minimize|maximize|list"},
         "title": {"type": "string"}}, ["action"]),
    _fn("get_special_folder", "Get the real path of a user folder (desktop, documents, downloads, pictures, music, videos, home). Use before file ops in these folders.",
        {"name": {"type": "string"}}, ["name"]),
    _fn("list_directory", "List files/folders in a directory.", {"path": {"type": "string"}}, ["path"]),
    _fn("read_file", "Read a text file's contents.", {"path": {"type": "string"}}, ["path"]),
    _fn("write_file", "Create/overwrite a text file with content (to save notes/documents). Confirms first.",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("delete_file", "Delete one specific file. Confirms first.", {"path": {"type": "string"}}, ["path"]),
    _fn("delete_files", "Delete multiple files in a folder matching a glob (e.g. *.txt). Confirms first.",
        {"folder": {"type": "string"}, "pattern": {"type": "string"}}, ["folder", "pattern"]),
    _fn("create_folder", "Create a folder.", {"path": {"type": "string"}}, ["path"]),
    _fn("copy_path", "Copy a file or folder.", {"source": {"type": "string"}, "destination": {"type": "string"}}, ["source", "destination"]),
    _fn("move_path", "Move a file or folder. Confirms first.", {"source": {"type": "string"}, "destination": {"type": "string"}}, ["source", "destination"]),
    _fn("rename_path", "Rename a file or folder. Confirms first.", {"path": {"type": "string"}, "new_name": {"type": "string"}}, ["path", "new_name"]),
    _fn("search_files", "Search for files matching a pattern in a folder (recursive by default).",
        {"folder": {"type": "string"}, "pattern": {"type": "string"}, "recursive": {"type": "boolean"}}, ["folder", "pattern"]),
    _fn("set_volume", "Set system volume to a percentage (0-100).", {"percent": {"type": "integer"}}, ["percent"]),
    _fn("media_control", "Media keys: playpause, next, previous, stop, mute, volume_up, volume_down.",
        {"action": {"type": "string"}}, ["action"]),
    _fn("set_brightness", "Set screen brightness percentage (0-100).", {"percent": {"type": "integer"}}, ["percent"]),
    _fn("power_control", "Lock, sleep, restart, or shutdown. Sleep/restart/shutdown confirm first.",
        {"action": {"type": "string"}}, ["action"]),
    _fn("get_battery", "Get battery charge percentage."),
    _fn("get_system_info", "Get OS, total RAM, free memory."),
    _fn("run_powershell", "Run an arbitrary PowerShell command for tasks no other tool covers. Confirms first.",
        {"command": {"type": "string"}}, ["command"]),
    _fn("get_datetime", "Get the current date and time."),
]


def dispatch(name, args):
    if name not in FUNCS:
        return f"Unknown tool: {name}"
    args = args or {}
    _audit(f"CALL {name} {args}")
    try:
        result = FUNCS[name](**args)
    except TypeError as e:
        result = f"Bad arguments for {name}: {e}"
    except Exception as e:
        result = f"Tool {name} failed: {e}"
    _audit(f"RESULT {name}: {str(result)[:200]}")
    return result
