import os
from flask import Flask, render_template
import docker

app = Flask(__name__)
client = docker.from_env()

@app.route('/')
def index():
    all_containers = client.containers.list(all=True)
    
    # We will organize containers here
    groups = {
        "Immich": {
            "is_group": True,
            "services": [],
            "status": "exited", # Default
            "url": "http://192.168.1.50:2283" # Your Immich Web Port
        },
        "Other Apps": {
            "is_group": False,
            "services": []
        }
    }

    for c in all_containers:
        container_info = {
            "name": c.name,
            "status": c.status,
        }

        # Check if the container belongs to Immich
        if "immich" in c.name.lower():
            groups["Immich"]["services"].append(container_info)
            # If at least one part of Immich is running, show active status
            if c.status == "running":
                groups["Immich"]["status"] = "running"
        else:
            groups["Other Apps"]["services"].append(container_info)

    return render_template('index.html', groups=groups)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
