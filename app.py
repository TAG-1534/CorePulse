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

# The Correct CDN Base URL
ICON_BASE = "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png"

def get_icon_url(name):
    name = name.lower()
    # Manual mapping for common variations
    if "immich" in name: slug = "immich"
    elif "plex" in name: slug = "plex"
    elif "portainer" in name: slug = "portainer"
    elif "truenas" in name: slug = "truenas"
    elif "pihole" in name: slug = "pi-hole"
    elif "vaultstream" in name: slug = "docker" # or your specific app icon
    elif "mysql" in name or "mariadb" in name: slug = "mariadb"
    elif "postgres" in name: slug = "postgres"
    elif "redis" in name: slug = "redis"
    else: slug = "docker" # Default
    
    return f"{ICON_BASE}/{slug}.png"

@app.route('/')
def index():
    all_containers = client.containers.list(all=True)
    groups = {
        "Immich": {"services": [], "status": "exited", "icon_url": get_icon_url("immich")},
        "Apps": []
    }

    for c in all_containers:
        # Clean up the name (remove leading slash)
        clean_name = c.name.lstrip('/')
        icon_url = get_icon_url(clean_name)
        
        if "immich" in clean_name.lower():
            groups["Immich"]["services"].append({"name": clean_name, "status": c.status})
            if c.status == "running": groups["Immich"]["status"] = "running"
        else:
            groups["Apps"].append({
                "name": clean_name, 
                "status": c.status, 
                "icon_url": icon_url
            })

    # TrueNAS Logic
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            url = f"http://{TRUENAS_IP}/api/v2.0/pool"
            response = requests.get(url, headers=headers, timeout=3, verify=False)
            if response.status_code == 200:
                nas_stats["status"] = "Online"
                nas_stats["pools"] = response.json()
        except:
            pass

    return render_template('index.html', groups=groups, nas=nas_stats, tn_icon=get_icon_url("truenas"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
