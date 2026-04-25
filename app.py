import os
import docker
import requests
import urllib3
from flask import Flask, render_template

# Suppress SSL warnings for self-signed TrueNAS certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
client = docker.from_env()

# Get variables from Portainer .env
TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

@app.route('/')
def index():
    # Docker logic (Same as before)
    all_containers = client.containers.list(all=True)
    groups = {"Immich": {"services": [], "status": "exited"}, "Apps": []}
    for c in all_containers:
        if "immich" in c.name.lower():
            groups["Immich"]["services"].append({"name": c.name, "status": c.status})
            if c.status == "running": groups["Immich"]["status"] = "running"
        else:
            groups["Apps"].append({"name": c.name, "status": c.status})

    # FIXED TrueNAS Logic
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            # We use verify=False because local TrueNAS certs aren't 'trusted'
            # We also ensure we use http or https based on your TrueNAS setting
            url = f"http://{TRUENAS_IP}/api/v2.0/pool" 
            response = requests.get(url, headers=headers, timeout=5, verify=False)
            
            if response.status_code == 200:
                nas_stats["status"] = "Online"
                nas_stats["pools"] = response.json()
            else:
                nas_stats["status"] = f"Error {response.status_code}"
        except Exception as e:
            nas_stats["status"] = "Connection Timeout"

    return render_template('index.html', groups=groups, nas=nas_stats)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
