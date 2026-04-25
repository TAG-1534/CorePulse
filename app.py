import os
import docker
import requests
import urllib3
from flask import Flask, render_template

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
client = docker.from_env()

TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

# --- CUSTOMIZE THIS ---
# Map your container names to their local ports
PORT_MAP = {
    "immich_server": "2283",
    "plex": "32400",
    "pihole": "80",
    "portainer": "9000",
    "vaultstream": "5005"
}
def format_bytes(size):
    # Convert bytes to human readable format (GB or TB)
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)}{power_labels[n]}B"

# Inside your @app.route('/') under the TrueNAS logic:
for p in r.json():
    stats = p.get('topology', {}).get('data', [{}])[0].get('stats', {})
    total_raw = stats.get('size', 0)
    alloc_raw = stats.get('allocated', 0)
    free_raw = total_raw - alloc_raw
    
    percent = round((alloc_raw / total_raw) * 100, 1) if total_raw > 0 else 0
    
    nas_stats["pools"].append({
        "name": p['name'],
        "status": p['status'],
        "used_str": format_bytes(alloc_raw),
        "total_str": format_bytes(total_raw),
        "free_str": format_bytes(free_raw),
        "raw_percent": percent
    })
    
def get_icon_url(name):
    name = name.lower()
    ICON_BASE = "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png"
    if "immich" in name: slug = "immich"
    elif "plex" in name: slug = "plex"
    elif "portainer" in name: slug = "portainer"
    elif "truenas" in name: slug = "truenas"
    else: slug = "docker"
    return f"{ICON_BASE}/{slug}.png"

@app.route('/')
def index():
    all_containers = client.containers.list(all=True)
    groups = {"Immich": {"services": [], "status": "exited", "url": ""}, "Apps": []}
    
    # Set Immich default URL if it exists in map
    groups["Immich"]["url"] = f"http://{TRUENAS_IP}:{PORT_MAP.get('immich_server', '2283')}"

    for c in all_containers:
        name = c.name.lstrip('/')
        # Get port from map, default to # if not found
        port = PORT_MAP.get(name, "")
        url = f"http://{TRUENAS_IP}:{port}" if port else "#"

        if "immich" in name.lower():
            groups["Immich"]["services"].append({"name": name, "status": c.status})
            if c.status == "running": groups["Immich"]["status"] = "running"
        else:
            groups["Apps"].append({
                "name": name, 
                "status": c.status, 
                "icon_url": get_icon_url(name),
                "url": url
            })

    # TrueNAS Storage Logic
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            # We hit /pool to get topology and usage
            r = requests.get(f"http://{TRUENAS_IP}/api/v2.0/pool", headers=headers, timeout=3, verify=False)
            if r.status_code == 200:
                nas_stats["status"] = "Online"
                for p in r.json():
                    # Calculate usage if data exists
                    total = p.get('topology', {}).get('data', [{}])[0].get('stats', {}).get('size', 0)
                    allocated = p.get('topology', {}).get('data', [{}])[0].get('stats', {}).get('allocated', 0)
                    percent = round((allocated / total) * 100, 1) if total > 0 else 0
                    
                    nas_stats["pools"].append({
                        "name": p['name'],
                        "status": p['status'],
                        "usage": f"{percent}%",
                        "raw_percent": percent
                    })
        except: pass

    return render_template('index.html', groups=groups, nas=nas_stats, nas_ip=TRUENAS_IP)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
