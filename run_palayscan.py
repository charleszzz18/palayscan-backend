import os
import re
import sys
import time
import ctypes
import subprocess
import webbrowser
import threading
import urllib.request
import urllib.error

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
CLOUDFLARED = os.path.join(ROOT_DIR, "cloudflared.exe")
API_CONFIG = os.path.join(FRONTEND_DIR, "api_config.js")

# --- 1. WINDOWS POWER MANAGEMENT (PREVENT IDLE SLEEP) ---
ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001

def prevent_sleep():
    """Tells Windows not to enter sleep mode while the server is actively running."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        pass

def allow_sleep():
    """Restores standard Windows power management when the server exits."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass

# --- 2. CLEANUP HELPERS ---
def kill_existing_cloudflared():
    """Cleans up any orphaned cloudflared processes from prior sessions."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

# --- 3. CONFIGURATION & GITHUB SYNC ---
def update_api_config(url):
    """Writes the active tunnel URL into api_config.js."""
    content = f"""// =========================================================================
// PALAYSCAN API CONFIGURATION
// =========================================================================
// Auto-configured by PalayScan Launcher
const API_BASE_URL = '{url}';
"""
    with open(API_CONFIG, "w", encoding="utf-8") as f:
        f.write(content)

def sync_to_github_for_vercel(url):
    """Automatically commits and pushes the new tunnel URL to GitHub so Vercel redeploys."""
    try:
        subprocess.run(["git", "add", "frontend/api_config.js", "vercel.json"],
                       cwd=ROOT_DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = subprocess.run(["git", "commit", "-m", f"Auto-sync API URL for Vercel: {url}"],
                             cwd=ROOT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            subprocess.run(["git", "push", "origin", "master:main"],
                           cwd=ROOT_DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "master"],
                           cwd=ROOT_DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("   [+] Vercel auto-sync: Pushed new URL to GitHub successfully!")
    except Exception as e:
        print(f"   [!] Vercel sync notice: {e}")

# --- 4. CLOUDFLARE PROCESS LAUNCHER ---
def launch_cloudflared_tunnel():
    """Starts cloudflared with HTTP/2 (TCP port 443) to prevent ISP/router NAT timeouts."""
    if not os.path.exists(CLOUDFLARED):
        print(f"Error: cloudflared.exe not found at {CLOUDFLARED}")
        return None, None

    cf_proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:5000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )

    tunnel_url = None
    start_time = time.time()
    while time.time() - start_time < 35:
        line = cf_proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
        if match:
            tunnel_url = match.group(0)
            break

    return cf_proc, tunnel_url

# --- 5. TUNNEL HEALTH CHECK ---
def check_tunnel_health(url):
    """Sends a fast lightweight ping to the public URL to ensure Cloudflare edge reaches Flask."""
    if not url or not url.startswith("https://"):
        return False
    try:
        req = urllib.request.Request(
            f"{url}/",
            headers={"User-Agent": "PalayScan-Watchdog/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 301, 302, 401, 403, 404)
    except urllib.error.HTTPError as e:
        # If Flask responds with any HTTP error code (e.g. 401/404), the tunnel is healthy!
        return e.code in (200, 301, 302, 400, 401, 403, 404, 405)
    except Exception:
        return False

# --- 6. MAIN APPLICATION CONTROLLER ---
def main():
    print("=" * 65)
    print("   [+] PALAYSCAN - ENHANCED SERVER LAUNCHER (METHOD 1) [+]")
    print("=" * 65)

    prevent_sleep()
    kill_existing_cloudflared()

    print("[1/3] Starting backend Flask server on port 5000...")
    flask_proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=BACKEND_DIR
    )
    time.sleep(3)

    print("[2/3] Starting Cloudflare tunnel (HTTP/2 stable protocol)...")
    cf_proc, tunnel_url = launch_cloudflared_tunnel()

    if not tunnel_url:
        print("\n[!] Failed to get Cloudflare Tunnel URL within 35 seconds.")
        print("Falling back to local address: http://localhost:5000")
        tunnel_url = "http://localhost:5000"
    else:
        print("[3/3] Establishing public worldwide HTTPS link...")
        update_api_config(tunnel_url)
        threading.Thread(target=sync_to_github_for_vercel, args=(tunnel_url,), daemon=True).start()

    print("\n" + "=" * 65)
    print("   [OK] PALAYSCAN IS NOW LIVE AND READY!")
    print("=" * 65)
    print(f"\n   [*] Public Link (Share with anyone on any phone/PC):")
    print(f"       ->  {tunnel_url}\n")
    print(f"   [*] Local Link (For this PC):")
    print(f"       ->  http://localhost:5000\n")
    print("=" * 65)
    print("   [i] Keep this window open while using the app.")
    print("   [i] Automatic watchdog enabled: Tunnel will auto-revive if disconnected.")
    print("   [i] Windows Sleep Prevention: Active (system will stay awake).")
    print("   [i] Press CTRL + C to stop the server anytime.")
    print("=" * 65 + "\n")

    try:
        webbrowser.open(tunnel_url)
    except Exception:
        pass

    consecutive_failures = 0
    last_health_log = time.time()

    try:
        while True:
            time.sleep(20)  # Check every 20 seconds (also acts as keep-alive traffic)

            # Check if Flask crashed
            if flask_proc.poll() is not None:
                print("\n[!] Flask server stopped unexpectedly. Exiting...")
                break

            # If using local fallback, no Cloudflare watchdog needed
            if "trycloudflare.com" not in tunnel_url:
                continue

            # Run health ping
            is_healthy = check_tunnel_health(tunnel_url)

            if is_healthy:
                consecutive_failures = 0
                # Log a heartbeat confirmation every 15 minutes
                if time.time() - last_health_log > 900:
                    print(f"[{time.strftime('%H:%M:%S')}] Tunnel heartbeat: Connection healthy ({tunnel_url})")
                    last_health_log = time.time()
            else:
                consecutive_failures += 1
                print(f"[{time.strftime('%H:%M:%S')}] Tunnel health warning ({consecutive_failures}/3 failed checks)...")

                if consecutive_failures >= 3:
                    print("\n" + "!" * 65)
                    print(f"[{time.strftime('%H:%M:%S')}] [WATCHDOG] Cloudflare tunnel lost connection!")
                    print("   [+] Auto-restarting Cloudflare tunnel now...")
                    print("!" * 65)

                    # Kill the dead tunnel
                    try:
                        cf_proc.terminate()
                        cf_proc.kill()
                    except Exception:
                        pass
                    kill_existing_cloudflared()
                    time.sleep(2)

                    # Relaunch a fresh tunnel
                    cf_proc, new_url = launch_cloudflared_tunnel()
                    if new_url:
                        tunnel_url = new_url
                        print(f"   [+] New Active Tunnel URL: {tunnel_url}")
                        update_api_config(tunnel_url)
                        sync_to_github_for_vercel(tunnel_url)
                        print("   [+] Watchdog: Recovery complete! System is back online.")
                    else:
                        print("   [!] Watchdog: Reconnection attempt failed. Will retry in 20s...")

                    consecutive_failures = 0
                    last_health_log = time.time()

    except KeyboardInterrupt:
        print("\nShutting down PalayScan...")
    finally:
        allow_sleep()
        try:
            flask_proc.terminate()
        except Exception:
            pass
        try:
            if cf_proc:
                cf_proc.terminate()
        except Exception:
            pass
        kill_existing_cloudflared()
        print("Shutdown complete. Goodbye!")

if __name__ == "__main__":
    main()
