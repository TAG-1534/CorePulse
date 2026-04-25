import os
from flask import Flask, render_template, jsonify
import docker
import requests

app = Flask(__name__)
client = docker.from_env()

# Config from environment variables (set these in Portainer)
TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

@app.route('/')
def index():
    # Fetch Docker Containers
    containers = []
    for c in client.containers.list(all=True):
        containers.append({
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else "N/A"
        })
    return render_template('index.html', containers=containers, tn_ip=TRUENAS_IP)

@app.route('/api/stats')
def stats():
    # Fetch TrueNAS Pool/System Info
    headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
    try:
        # Example endpoint for system info (adjust for SCALE/CORE)
        response = requests.get(f"http://{TRUENAS_IP}/api/v2.0/system/info", headers=headers, timeout=3)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
