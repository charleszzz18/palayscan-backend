# =========================================================================
# GUNICORN CONFIGURATION (gunicorn.conf.py)
# =========================================================================
# Custom production server settings optimized for Render Free Tier (512MB RAM).

# Worker timeout in seconds. Gives ample time for model cold starts and image inference.
timeout = 120

# Run 1 worker process to ensure RAM usage stays well below the 512MB container limit.
workers = 1

# 2 threads per worker allow concurrent non-blocking requests.
threads = 2

# Keep-alive timeout
keepalive = 5

# Preload app so model is loaded into memory before worker forks
preload_app = False
