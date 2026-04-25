import os
# This MUST come before importing psutil to work correctly in Docker
os.environ['PROCFS_PATH'] = '/host/proc'

import docker
import requests
import urllib3
import psutil
from flask import Flask, render_template, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
client = docker.from_env()

TRUENAS_IP = os.getenv("TRUENAS_IP")
TRUENAS_API_KEY = os.getenv("TRUENAS_API_KEY")

# Proxmox Config
PROXMOX_URL = os.getenv("PROXMOX_URL")
PROXMOX_NODE = os.getenv("PROXMOX_NODE")
PROXMOX_TOKEN_ID = os.getenv("PROXMOX_TOKEN_ID")
PROXMOX_TOKEN_SECRET = os.getenv("PROXMOX_TOKEN_SECRET")

PORT_MAP = {
    "immich_server": "2283",
    "plex": "32400",
    "pihole": "80",
    "portainer": "9000",
    "vaultstream": "5005"
}

def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)}{power_labels[n]}B"

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
        # The standard Proxmox API path for QEMU (VMs)
        r = requests.get(f"{PROXMOX_URL}/api2/json/nodes/{PROXMOX_NODE}/qemu", headers=headers, verify=False, timeout=2)
        if r.status_code == 200:
            vms = []
            for vm in r.json()['data']:
                cpu = round(vm.get('cpu', 0) * 100, 1)
                max_mem = vm.get('maxmem', 1)
                curr_mem = vm.get('mem', 0)
                mem_pct = round((curr_mem / max_mem) * 100, 1) if max_mem > 0 else 0
                # Update the vms.append section in your get_proxmox_stats function:
                vms.append({
                    "name": vm['name'],
                    "status": vm['status'],
                    "vmid": vm['vmid'],
                    "cpu": cpu,
                    "mem_pct": mem_pct,
                    "mem_used": format_bytes(curr_mem),  # Already there
                    "mem_max": format_bytes(max_mem)     # Add this line
                })
            return sorted(vms, key=lambda x: x['vmid'])
    except Exception as e:
        print(f"Proxmox Error: {e}")
    return []

@app.route('/api/stats')
def api_stats():
    vm = psutil.virtual_memory()
    system_stats = {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "ram_percent": vm.percent,
        "ram_used": format_bytes(vm.used),
        "ram_total": format_bytes(vm.total)
    }
    # Including Proxmox in the live update
    vm_list = get_proxmox_stats()
    return jsonify({
        "system": system_stats,
        "vms": vm_list
    })

@app.route('/')
def index():
    # --- Host System Stats ---
    vm = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq()
    system_stats = {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_mhz": round(cpu_freq.current, 0) if cpu_freq else "N/A",
        "ram_total": format_bytes(vm.total),
        "ram_used": format_bytes(vm.used),
        "ram_free": format_bytes(vm.available),
        "ram_percent": vm.percent
    }

    # --- Proxmox Logic ---
    vm_list = get_proxmox_stats()

    # --- Docker Logic ---
    all_containers = client.containers.list(all=True)
    groups = {"Immich": {"services": [], "status": "exited", "url": ""}, "Apps": []}
    groups["Immich"]["url"] = f"http://{TRUENAS_IP}:{PORT_MAP.get('immich_server', '2283')}"

    for c in all_containers:
        name = c.name.lstrip('/')
        port = PORT_MAP.get(name, "")
        url = f"http://{TRUENAS_IP}:{port}" if port else "#"
        if "immich" in name.lower():
            groups["Immich"]["services"].append({"name": name, "status": c.status})
            if c.status == "running": groups["Immich"]["status"] = "running"
        else:
            groups["Apps"].append({
                "name": name, "status": c.status, 
                "icon_url": get_icon_url(name), "url": url
            })

   # --- TrueNAS Storage Logic ---
    nas_stats = {"status": "Disconnected", "pools": []}
    if TRUENAS_IP and TRUENAS_API_KEY:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        try:
            r = requests.get(f"http://{TRUENAS_IP}/api/v2.0/pool", headers=headers, timeout=3, verify=False)
            if r.status_code == 200:
                nas_stats["status"] = "Online"
                for p in r.json():
                    topology = p.get('topology', {})
                    data_vdevs = topology.get('data', [])
                    total_raw = sum(v.get('stats', {}).get('size', 0) for v in data_vdevs)
                    alloc_raw = sum(v.get('stats', {}).get('allocated', 0) for v in data_vdevs)
                    percent = round((alloc_raw / total_raw) * 100, 1) if total_raw > 0 else 0
                    nas_stats["pools"].append({
                        "name": p['name'], "status": p['status'],
                        "used_str": format_bytes(alloc_raw),
                        "total_str": format_bytes(total_raw),
                        "free_str": format_bytes(total_raw - alloc_raw),
                        "raw_percent": percent
                    })
        except Exception as e:
            print(f"Error connecting to TrueNAS: {e}")

    return render_template('index.html', 
                           groups=groups, 
                           nas=nas_stats, 
                           system=system_stats, 
                           vms=vm_list,
                           nas_ip=TRUENAS_IP)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
