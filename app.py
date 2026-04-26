import os
# This MUST come before importing psutil to work correctly in Docker
os.environ['PROCFS_PATH'] = '/host/proc'

import docker
import requests
import urllib3
import psutil
import re
from flask import Flask, render_template, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
client = docker.from_env()

# --- Configuration ---
TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

PROXMOX_URL = os.getenv("PROXMOX_URL")
PROXMOX_NODE = os.getenv("PROXMOX_NODE")
PROXMOX_TOKEN_ID = os.getenv("PROXMOX_TOKEN_ID")
PROXMOX_TOKEN_SECRET = os.getenv("PROXMOX_TOKEN_SECRET")

PORTAINER_IP = os.getenv("PORTAINER_IP")
PORTAINER_API_KEY = os.getenv('PORTAINER_API_KEY') 
ENDPOINT_ID = os.getenv('ENDPOINT_ID', '1')

# This maps container names to their WEB ports for the dashboard links
PORT_MAP = {
    "immich_server": {"port": "2283", "proto": "http"},
    "plex": {"port": "32400", "proto": "http"},
    "pihole": {"port": "80", "proto": "http"},
    "portainer": {"port": "9443", "proto": "https"},
    "vaultstream": {"port": "5005", "proto": "http"}
}

# --- Helper Functions ---
def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)}{power_labels[n]}B"

def clean_name(name):
    name = re.sub(r'[-_]', ' ', name)
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return name.title()

def get_icon_url(name):
    name = name.lower()
    ICON_BASE = "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png"
    if "immich" in name: slug = "immich"
    elif "plex" in name: slug = "plex"
    elif "portainer" in name: slug = "portainer"
    elif "truenas" in name: slug = "truenas"
    else: slug = "docker"
    return f"{ICON_BASE}/{slug}.png"

def get_proxmox_stats():
    if not all([PROXMOX_URL, PROXMOX_NODE, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET]):
        return []
    headers = {"Authorization": f"PVEAPIToken={PROXMOX_TOKEN_ID}={PROXMOX_TOKEN_SECRET}"}
    try:
        r = requests.get(f"{PROXMOX_URL}/api2/json/nodes/{PROXMOX_NODE}/qemu", headers=headers, verify=False, timeout=2)
        if r.status_code == 200:
            vms = []
            for vm in r.json()['data']:
                cpu = round(vm.get('cpu', 0) * 100, 1)
                max_mem = vm.get('maxmem', 1)
                curr_mem = vm.get('mem', 0)
                mem_pct = round((curr_mem / max_mem) * 100, 1) if max_mem > 0 else 0
                vms.append({
                    "name": vm['name'],
                    "status": vm['status'],
                    "vmid": vm['vmid'],
                    "cpu": cpu,
                    "mem_pct": mem_pct,
                    "mem_used": format_bytes(curr_mem),
                    "mem_max": format_bytes(max_mem),
                    "console_url": f"{PROXMOX_URL}/#v1:0:18:4::{vm['vmid']}"
                })
            return sorted(vms, key=lambda x: x['vmid'])
    except Exception as e:
        print(f"Proxmox Error: {e}")
    return []

# --- Routes ---

@app.route('/api/container/<container_id>/<action>', methods=['POST'])
def container_control(container_id, action):
    """
    Controls Docker containers via the Portainer API.
    Action: start, stop, restart
    """
    if not PORTAINER_IP or not PORTAINER_API_KEY:
        return jsonify({"error": "Portainer credentials missing"}), 500

    # Portainer API uses port 9443 (HTTPS) or 9000 (HTTP) by default. 
    # This is distinct from the apps' own ports in PORT_MAP.
    portainer_base = f"https://{PORTAINER_IP}:9443" 
    url = f"{portainer_base}/api/endpoints/{ENDPOINT_ID}/docker/containers/{container_id}/{action}"
    
    headers = {"X-API-Key": PORTAINER_API_KEY}
    
    try:
        # Use verify=False if using self-signed certs on Portainer
        response = requests.post(url, headers=headers, verify=False, timeout=5)
        return jsonify({"status": "success", "portainer_response": response.status_code}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def api_stats():
    vm = psutil.virtual_memory()
    system_stats = {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "ram_percent": vm.percent,
        "ram_used": format_bytes(vm.used),
        "ram_total": format_bytes(vm.total)
    }
    vm_list = get_proxmox_stats()
    return jsonify({
        "system": system_stats,
        "vms": vm_list
    })

@app.route('/')
def index():
    # --- Host System Stats ---
    vm = psutil.virtual_memory()
    system_stats = {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "ram_percent": vm.percent,
        "ram_used": format_bytes(vm.used),
        "ram_total": format_bytes(vm.total)
    }

    # --- Proxmox Logic ---
    vm_list = get_proxmox_stats()

    # --- Docker Logic ---
    all_containers = client.containers.list(all=True)
    
    # NEW: Sort alphabetically by container name
    all_containers.sort(key=lambda c: c.name.lstrip('/').lower())

    # NEW: Replaced "Apps" with "Running" and "Stopped" lists
    groups = {
        "Immich": {"services": [], "status": "exited", "url": "", "name": "Immich Photos", "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/immich.png"}, 
        "Running": [],
        "Stopped": []
    }
    
    immich_cfg = PORT_MAP.get("immich_server", {"port": "2283", "proto": "http"})
    groups["Immich"]["url"] = f"{immich_cfg['proto']}://{PORTAINER_IP}:{immich_cfg['port']}"

    for c in all_containers:
        raw_name = c.name.lstrip('/')
        display_name = clean_name(raw_name)
        config = PORT_MAP.get(raw_name) or PORT_MAP.get(raw_name.lower())
        
        url = "#"
        if config:
            proto = config.get("proto", "http")
            port = config.get("port", "")
            url = f"{proto}://{PORTAINER_IP}:{port}"

        image_name = c.image.tags[0] if c.image.tags else "Unknown Image"
        
        container_data = {
            "id": c.id,
            "name": display_name, 
            "status": c.status, 
            "icon_url": get_icon_url(raw_name), 
            "url": url,
            "image": image_name,
            "address": url
        }

        # NEW: Check for Immich first, then sort the rest into Running/Stopped
        if "immich" in raw_name.lower():
            groups["Immich"]["services"].append(container_data)
            if c.status == "running":
                groups["Immich"]["status"] = "running"
        else:
            if c.status == "running":
                groups["Running"].append(container_data)
            else:
                groups["Stopped"].append(container_data)

    # --- TrueNAS Storage Logic ---
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            # We use the /pool endpoint
            r = requests.get(f"http://{TRUENAS_IP}/api/v2.0/pool", headers=headers, timeout=3)
            if r.status_code == 200:
                nas_stats["status"] = "Online"
                for p in r.json():
                    # TrueNAS SCALE usually provides usage in a nested 'usage' dict
                    # But some versions might provide 'size' and 'allocated' in 'stats'
                    usage = p.get('usage', {})
                    
                    # Fallback chain for Total Size
                    total_bytes = usage.get('total') or p.get('size') or 1
                    
                    # Fallback chain for Used Size
                    used_bytes = usage.get('used') or p.get('allocated') or 0
                    
                    # Calculate percentage safely
                    percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
                    
                    nas_stats["pools"].append({
                        "name": p.get('name', 'Unknown Pool'),
                        "status": p.get('status', 'HEALTHY'),
                        "used_str": format_bytes(used_bytes),
                        "total_str": format_bytes(total_bytes),
                        "raw_percent": percent
                    })
            else:
                print(f"TrueNAS API returned status: {r.status_code}")
        except Exception as e:
            print(f"TrueNAS Error: {e}")

    return render_template('index.html', 
                           groups=groups, 
                           nas=nas_stats, 
                           system=system_stats, 
                           vms=vm_list,
                           nas_ip=TRUENAS_IP,
                           PROXMOX_URL=PROXMOX_URL)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
