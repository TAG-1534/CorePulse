import os
from flask import Flask, render_template
import docker

app = Flask(__name__)
client = docker.from_env()

def get_icon(name):
    # Mapping common names to dashboard-icons slugs
    name = name.lower()
    if "immich" in name: return "immich"
    if "plex" in name: return "plex"
    if "portainer" in name: return "portainer"
    if "truenas" in name: return "truenas"
    if "vaultstream" in name: return "favicon" # fallback or custom
    return "docker"

@app.route('/')
def index():
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

    return render_template('index.html', groups=groups)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
