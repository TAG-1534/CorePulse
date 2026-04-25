import os
from flask import Flask, render_template, jsonify
import docker
import requests

app = Flask(__name__)
client = docker.from_env()

# These will now be pulled from Portainer's "Environment Variables" section
TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

def get_icon(name):
    name = name.lower()
    if "immich" in name: return "immich"
    if "plex" in name: return "plex"
    if "portainer" in name: return "portainer"
    if "truenas" in name: return "truenas"
    if "pihole" in name: return "pi-hole"
    return "docker"

@app.route('/')
def index():
    # 1. Fetch Docker Containers
    all_containers = client.containers.list(all=True)
    groups = {
        "Immich": {"services": [], "status": "exited", "icon": "immich"},
        "Apps": []
    }

    for c in all_containers:
        icon = get_icon(c.name)
        if "immich" in c.name.lower():
            groups["Immich"]["services"].append({"name": c.name, "status": c.status})
            if c.status == "running": groups["Immich"]["status"] = "running"
        else:
            groups["Apps"].append({"name": c.name, "status": c.status, "icon": icon})

    # 2. Fetch TrueNAS Storage Info
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            # Fetching Pool information
            response = requests.get(f"http://{TRUENAS_IP}/api/v2.0/pool", headers=headers, timeout=2)
            if response.status_code == 200:
                nas_stats["status"] = "Online"
                nas_stats["pools"] = response.json()
        except:
            nas_stats["status"] = "Error Connecting"

    return render_template('index.html', groups=groups, nas=nas_stats)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
