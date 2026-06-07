# Deployr

Deployr is an interactive CLI tool for managing Python/Flask web services, running Kubernetes jobs, and establishing SSH database tunnels on Wikimedia Toolforge.

It automates SSH terminal switching, workspace permissions resolution, and handles modern Toolforge Python environments by offloading virtualenv builds to Kubernetes staging jobs.

## Prerequisites

* A Wikimedia Developer account (Wikitech).
* Your public SSH key registered in Wikitech preferences.
* A registered Toolforge tool account.

## Setup

Make the manager script executable:
```bash
chmod +x toolforge_manager.py
```

On first execution, the tool will prompt for your configuration details and write them to `~/.toolforge_config.json`:
```json
{
    "username": "wikimedia_username",
    "tool_name": "tool_name",
    "ssh_key": "~/.ssh/id_rsa",
    "bastion_host": "login.toolforge.org"
}
```

## Usage

Start the interactive console:
```bash
./toolforge_manager.py
```

### Main Options

* **1. SSH to Bastion**: Opens an interactive SSH terminal connected to `login.toolforge.org`.
* **2. Switch to Tool Shell**: Opens an interactive shell switched directly to the tool's environment (`become <tool_name>`).
* **3. Web Service Control**: Sub-menu to view status, start, stop, restart, or deploy Flask apps.
* **4. Kubernetes Jobs**: Sub-menu to run, list, delete, or inspect container logs for jobs.
* **5. Upload Files**: SCP files/folders from your local machine to the tool's home folder.
* **6. SSH Database Tunnel**: Bypasses Toolforge network restrictions by establishing a secure port-forwarded tunnel (default port 3306) to query private Wikimedia database servers locally.

## Deploying Python/Flask Apps

Under **3. Web Service Control Menu**, select option **5. Deploy Python/Flask Web App**.

### How it works:
1. **Packaging**: Bundles either a single entry file or your entire local project directory (excluding `.git`, `__pycache__`, local `.venv`, `node_modules`).
2. **Wrapper Generation**: If your entry file is not named `app.py` or the Flask instance variable is not `app`, Deployr writes an `app.py` wrapper to interface cleanly with uWSGI.
3. **Workspace Staging**: Pre-clears old code paths on the server using your personal account to resolve potential permission blocks, then copies new assets to `~/www/python/src/`.
4. **Venv Provisioning**: If a `requirements.txt` is found, Deployr launches a temporary Kubernetes job on the cluster using the matching python image. This creates a clean `venv` at `~/www/python/venv`, bootstraps `pip` dynamically (resolving missing `ensurepip` on the host OS), and installs requirements.
5. **Restart**: Restarts the uWSGI webservice on Kubernetes to serve the updated build.
