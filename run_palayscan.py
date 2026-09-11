import os
import re
import sys
import time
import subprocess
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
CLOUDFLARED = os.path.join(ROOT_DIR, "cloudflared.exe")
API_CONFIG = os.path.join(FRONTEND_DIR, "api_config.js")

def update_api_config(url):
    content = f"""// =========================================================================
// PALAYSCAN API CONFIGURATION
// =========================================================================
// Auto-configured by PalayScan Launcher
const API_BASE_URL = '{url}';
"""
    with open(API_CONFIG, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    print("=" * 60)
    print("   [+] PALAYSCAN - AUTOMATIC SERVER LAUNCHER [+]")
    print("=" * 60)
    print("[1/3] Starting backend Flask server on port 5000...")
    
    # Start Flask backend
    flask_proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=BACKEND_DIR
    )
    
    # Give Flask a brief moment to bind to port 5000
    time.sleep(2)
    
    print("[2/3] Starting Cloudflare secure tunnel...")
    if not os.path.exists(CLOUDFLARED):
        print(f"Error: cloudflared.exe not found at {CLOUDFLARED}")
        flask_proc.terminate()
        return

    cf_proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", "http://localhost:5000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )

    tunnel_url = None
    print("[3/3] Establishing public worldwide HTTPS link...")
    
    start_time = time.time()
    while time.time() - start_time < 30:
        line = cf_proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
        if match:
            tunnel_url = match.group(0)
            break
            
    if not tunnel_url:
        print("\n[!] Failed to get Cloudflare Tunnel URL within 30 seconds.")
        print("Falling back to local address: http://localhost:5000")
        tunnel_url = "http://localhost:5000"
    else:
        # Update api_config.js with the new URL
        update_api_config(tunnel_url)

    print("\n" + "=" * 60)
    print("   [OK] PALAYSCAN IS NOW LIVE AND READY!")
    print("=" * 60)
    print(f"\n   [*] Public Link (Share with anyone on any phone/PC):")
    print(f"       ->  {tunnel_url}\n")
    print(f"   [*] Local Link (For this PC):")
    print(f"       ->  http://localhost:5000\n")
    print("=" * 60)
    print("   [i] Keep this window open while using the app.")
    print("   [i] Press CTRL + C to stop the server anytime.")
    print("=" * 60 + "\n")

    # Automatically open browser to the link
    try:
        webbrowser.open(tunnel_url)
    except Exception:
        pass

    try:
        # Keep running and stream tunnel health
        while True:
            time.sleep(1)
            if flask_proc.poll() is not None:
                print("Flask server stopped unexpectedly.")
                break
            if cf_proc.poll() is not None:
                print("Cloudflare tunnel stopped.")
                break
    except KeyboardInterrupt:
        print("\nShutting down PalayScan...")
    finally:
        flask_proc.terminate()
        cf_proc.terminate()
        print("Shutdown complete. Goodbye!")

if __name__ == "__main__":
    main()
