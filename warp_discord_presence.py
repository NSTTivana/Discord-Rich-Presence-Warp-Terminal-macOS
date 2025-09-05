
#!/usr/bin/env python3
import os, time, json, pwd, fnmatch, psutil
from pathlib import Path
from pypresence import Presence, exceptions

# ------------------ CONFIG ------------------
CLIENT_ID   = os.environ.get("DISCORD_CLIENT_ID", "YOUR_DISCORD_APP_ID")
ASSET_LARGE = "warp"
STATUS_FILE = os.path.expanduser("~/.local/share/discord_rpc/status.json")
FOCUS_CFG   = os.path.expanduser("~/.config/warp_rpc/focus.json")
CHECK_EVERY = 5
WARP_PATH_MARKER = "/applications/warp.app/"
# --------------------------------------------

def shell_name():
    try:
        sh = pwd.getpwuid(os.getuid()).pw_shell
    except Exception:
        sh = os.environ.get("SHELL", "")
    return os.path.basename(sh or "").lower()

def shorten_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home): path = path.replace(home, "~", 1)
    return path if len(path) <= 40 else "…" + path[-39:]

def read_status():
    try:
        with open(STATUS_FILE, "r") as f: return json.load(f)
    except Exception: return {}

def load_focus_rules():
    try:
        with open(FOCUS_CFG, "r") as f: return (json.load(f).get("rules", []))
    except Exception: return []

def match_focus_rule(cwd: str, rules):
    if not cwd: return None
    p = str(Path(cwd).expanduser())
    for r in rules:
        for pat in r.get("match", []):
            pat_expanded = str(Path(os.path.expanduser(pat)))
            if fnmatch.fnmatch(p, pat_expanded): return r
    return None

def warp_running() -> bool:
    for p in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        try:
            exe = (p.info.get("exe") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if WARP_PATH_MARKER in exe or WARP_PATH_MARKER in cmd:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def discord_running() -> bool:
    for p in psutil.process_iter(["name"]):
        if "discord" in (p.info.get("name") or "").lower(): return True
    return False

def main():
    rpc, connected = None, False
    started = int(time.time())
    last_key = None

    while True:
        if not discord_running():
            if connected: print("[!] Discord closed, disconnecting RPC")
            connected, rpc = False, None
            time.sleep(3); continue

        if not connected:
            try:
                rpc = Presence(CLIENT_ID); rpc.connect()
                connected = True; print("[+] Connected to Discord RPC")
            except Exception as e:
                print(f"[!] Connect failed: {e}"); time.sleep(5); continue

        try:
            if warp_running():
                st = read_status()
                cwd, branch = st.get("cwd") or "", st.get("branch") or ""
                shell = shell_name()

                details = "command line"
                parts = [f"Using {shell.upper()}", "On Warp"]
                if cwd:    parts.append(shorten_path(cwd))
                if branch: parts.append(f"git:{branch}")
                state = " • ".join(parts)

                args = dict(
                    details=details, state=state,
                    large_image=ASSET_LARGE, large_text="Warp Terminal",
                    start=started,
                    buttons=[{"label":"Warp", "url":"https://warp.dev"}],
                )
                shell_small = {"zsh":"zsh", "bash":"bash", "fish":"fish"}.get(shell)
                if shell_small: args.update(small_image=shell_small, small_text=shell.upper())

                rule = match_focus_rule(cwd, load_focus_rules())
                if rule:
                    fmt = {"cwd": cwd, "cwd_short": shorten_path(cwd), "branch": branch, "shell": shell.upper()}
                    if rule.get("details"):     args["details"] = rule["details"].format(**fmt)
                    if rule.get("state"):       args["state"]   = rule["state"].format(**fmt)
                    if rule.get("large_image"): args["large_image"] = rule["large_image"]
                    if rule.get("small_image"):
                        args["small_image"] = rule["small_image"]
                        args["small_text"]  = rule.get("small_text", fmt["shell"])
                    if rule.get("buttons"):     args["buttons"] = rule["buttons"]
                    key = f"FOCUS:{rule.get('name','')}|{cwd}|{branch}"
                    if rule.get("reset_timer_on_enter", False) and key != last_key:
                        started = int(time.time()); args["start"] = started; last_key = key
                else:
                    key = f"NORMAL|{cwd}|{branch}"
                    if key != last_key: started = int(time.time()); args["start"] = started; last_key = key

                rpc.update(**args); print("[*] Updated:", args["details"], "|", args["state"])
            else:
                rpc.clear(); print("[*] Cleared presence")
        except exceptions.PipeClosed:
            print("[!] Pipe closed — reconnecting…"); connected, rpc = False, None
        except Exception as e:
            print(f"[!] Error:", e); connected, rpc = False, None

        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
