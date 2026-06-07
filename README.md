# 🌐 Deployr — Wikimedia Toolforge Deployment Suite

An advanced, interactive command-line utility to effortlessly manage, deploy, and maintain your Python & Flask web services, Kubernetes jobs, and secure port forwarding tunnels directly from your local terminal.

---

## 🚀 Why This Toolkit Exists
Interacting with Wikimedia Toolforge traditionally requires remembering complex, multi-step CLI commands across different system user accounts (your personal developer credentials vs. the tool's secure system context). 

This tool abstracts away the complexity by providing a **beautiful, unified, interactive terminal dashboard** that automates everything from authentication, file staging, and permissions adjustments, to self-healing dependency setups on Kubernetes.

---

## ✨ Key Features

### 1. 🛡️ Absolute Permission Healing
* Prevents standard Toolforge permission-denied errors by dynamically sweeping and re-creating deployment folders using a two-tier strategy (utilizing both your SSH user context and the tool's group context).

### 2. ⚡ Direct Flask/Python Deployments
* **Deploy any Flask layout**: Supports single-file or complex multi-file directories.
* **Auto-Generated wrappers**: Allows any entry file name (e.g. `server.py`) and Flask variable name (e.g. `backend`). It dynamically writes clean, circular-import-safe uWSGI entrypoints.
* **Cluster-Based Dependency Building**: Runs package installations (`pip install -r requirements.txt`) using automated, one-off Kubernetes jobs inside the cloud. This aligns package installation exactly with the target python container image and avoids missing package errors on the bastion host.
* **Self-Healing Virtual Environments**: Detects if your remote virtual environment is missing, broken, or misaligned due to OS migrations, and automatically re-bootstraps `pip` and installs requirements cleanly.

### 3. 🌐 SSH Port Forwarding & Database Tunnels
* Establish secure local SSH tunnels directly to private Toolforge database servers (e.g. `tools.db.svc.wikimedia.cloud` on port `3306`) with one click to let you debug and test databases from your local desktop client.

### 4. 📦 Kubernetes Job Scheduler
* Seamlessly submit scheduled cron tasks or one-off background jobs. View output/error logs directly from your local terminal.

---

## 📂 Project Structure
```text
toolforge_toolkit/
├── toolforge_manager.py       # Core interactive CLI suite
├── sample_flask_app/          # Sample 1: Default Flask application (app.py)
└── sample_flask_app_2/        # Sample 2: Advanced Flask application (server.py, using 'backend')
```

---

## 🛠️ Getting Started

### 📋 Prerequisites
1. A **Wikimedia Developer Account** (Wikitech).
2. Your public SSH Key registered in your [Wikitech Preferences](https://wikitech.wikimedia.org/wiki/Special:Preferences).
3. A registered tool account (e.g., `gautham-playground`).

### 🏃‍♂️ Running the Manager CLI
Make the script executable and launch it:
```bash
chmod +x /Users/gauthammohanraj/Developer/toolforge_toolkit/toolforge_manager.py
/Users/gauthammohanraj/Developer/toolforge_toolkit/toolforge_manager.py
```

*On your first run, the tool will prompt you for your Wikitech username, your tool's registered name, and your private SSH key location. These configurations will be saved locally under `~/.toolforge_config.json` for subsequent runs.*

---

## ⚡ How to Deploy a Flask Application

1. Open the CLI Console:
   ```bash
   /Users/gauthammohanraj/Developer/toolforge_toolkit/toolforge_manager.py
   ```
2. Navigate to **`3. Web Service Control Menu`**.
3. Select **`5. Deploy Python/Flask Web App`**.
4. Feed your local app information:
   * **Local entry file path**: e.g., `/Users/gauthammohanraj/Developer/toolforge_toolkit/sample_flask_app_2/server.py`
   * **Flask instance variable name**: e.g., `backend`
   * **Requirements file path**: Press **Enter** to accept the auto-detected `requirements.txt` path!
   * **Option**: Select **`2`** to upload the entire project directory.
   
Deployr handles the rest, copies files to `/www/python/src/`, provisions your virtual environment, and starts/restarts your service!

---

## 🔬 Under the Hood (Architecture)
Deployr utilizes a specialized cloud layout to achieve robust zero-error runs on Toolforge:

```text
Local Machine                          Bastion Host                               K8s Pods
-------------                          ------------                               --------
[toolforge_manager.py] --(SCP)--> [/tmp/tf_deploy_temp]
                                              |
                                     (SSH personal user)
                                      Clears folder locks
                                              |
                                      (become tools.user)
                                              |
                                              v
                                   [~/www/python/src/]  <--(Job Setup)--  [setup-venv K8s Job]
                                   (Hosts Flask + Code)                   - Creates Python 3.11 venv
                                                                          - Manually bootstraps pip
                                                                          - Installs requirements
```

1. **Staging**: Local folders are cleaned and SCP'd to `/tmp/` on the bastion with open read permissions.
2. **Pre-Sweep**: To avoid permission locks on existing directories owned by different users, your developer account is used to sweep old code folders.
3. **K8s Isolation**: Heavy compilation and dependency installation tasks are offloaded from the restricted bastion shell to a dedicated Kubernetes job, ensuring identical container dependencies.
4. **uWSGI Mapping**: Bridged uWSGI execution to map any user module and entrypoint safely to the default container executable structure.
