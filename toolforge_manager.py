#!/usr/bin/env python3
"""
Wikimedia Toolforge Manager Backend App
A Flask-based backend server and dashboard to deploy applications, run jobs,
control webservices, and manage Toolforge configurations.
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import uuid
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from flask import Flask, request, jsonify

CONFIG_FILE_NAME = ".toolforge_config.json"

app = Flask(__name__)

def get_config_path():
    """Returns the path to the configuration file in the user's home directory."""
    return Path.home() / CONFIG_FILE_NAME

def load_config():
    """Loads configuration from the home directory, or returns defaults."""
    config_path = get_config_path()
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config from {config_path}: {e}")
    return {
        "username": "",
        "tool_name": "",
        "ssh_key": "",
        "bastion_host": "login.toolforge.org"
    }

def save_config(config):
    """Saves the configuration to the user's home directory."""
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def verify_and_read_ssh_key(config):
    """Reads the SSH private key from the local device to verify access and format."""
    ssh_key_path = os.path.expanduser(config.get("ssh_key", ""))
    if not ssh_key_path:
        raise Exception("Local SSH key path is not configured.")
    if not os.path.exists(ssh_key_path):
        raise Exception(f"Local SSH key file not found at: {ssh_key_path}")
    try:
        with open(ssh_key_path, "r", encoding="utf-8") as f:
            key_content = f.read()
        if "PRIVATE KEY" not in key_content:
            raise Exception("Invalid private SSH key file format.")
        return key_content
    except Exception as e:
        raise Exception(f"Failed to read SSH key: {str(e)}")

def get_ssh_cmd_base(config, tty=False):
    """Constructs the base SSH command list with non-interactive options."""
    cmd = ["ssh"]
    if tty:
        cmd.append("-t")
    
    ssh_key = config.get("ssh_key")
    if ssh_key:
        cmd.extend(["-i", os.path.expanduser(ssh_key)])
    
    # Configure non-interactive options to prevent hanging in background
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes"
    ])
    
    username = config["username"]
    host = config["bastion_host"]
    cmd.append(f"{username}@{host}")
    return cmd

def get_scp_cmd_base(config, local_path, remote_path, recursive=True):
    """Constructs the base SCP command list."""
    cmd = ["scp"]
    if recursive:
        cmd.append("-r")
    
    ssh_key = config.get("ssh_key")
    if ssh_key:
        cmd.extend(["-i", os.path.expanduser(ssh_key)])
        
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes"
    ])
    
    cmd.extend([local_path, f"{config['username']}@{config['bastion_host']}:{remote_path}"])
    return cmd

def run_ssh_command_capture(config, command, as_tool=False):
    """
    Runs a command on the bastion host, optionally switching to the tool account.
    Returns (stdout, stderr, returncode).
    """
    ssh_base = get_ssh_cmd_base(config, tty=False)
    
    if as_tool:
        tool_name = config.get("tool_name")
        if not tool_name:
            return "", "Default tool name is not set", -1
        remote_cmd = f"sudo -i -u tools.{tool_name} {command}"
    else:
        remote_cmd = command
        
    ssh_base.append(remote_cmd)
    
    try:
        result = subprocess.run(ssh_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        return "", f"SSH command timed out: {e}", -1
    except Exception as e:
        return "", f"Failed to execute SSH command: {str(e)}", -1

def upload_to_bastion(config, local_path, remote_path):
    """
    Uploads a file or directory to the bastion.
    Returns (stdout, stderr, returncode).
    """
    cmd = get_scp_cmd_base(config, local_path, remote_path)
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        return "", f"SCP command timed out: {e}", -1
    except Exception as e:
        return "", f"Failed to execute SCP command: {str(e)}", -1

def download_source_files(url, target_dir):
    """
    Downloads or clones the source files from the given URL into target_dir.
    Supports Git repositories and Zip/Tarball archives.
    """
    url_lower = url.lower()
    
    # Check if it looks like a Git URL
    is_git = False
    if url_lower.endswith(".git") or "git@" in url_lower or "gerrit.wikimedia.org" in url_lower:
        is_git = True
    elif "github.com" in url_lower or "gitlab.com" in url_lower:
        if "/archive/" not in url_lower and "/zip/" not in url_lower and "/releases/" not in url_lower:
            is_git = True

    if is_git:
        print(f"Cloning Git repository from: {url}")
        result = subprocess.run(["git", "clone", url, target_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr or result.stdout}")
        return "git"

    # Treat it as a direct archive download
    print(f"Downloading archive from: {url}")
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_path = temp_file.name
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(temp_file_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        # Detect archive format and extract
        if zipfile.is_zipfile(temp_file_path):
            print("Extracting ZIP archive...")
            with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        elif tarfile.is_tarfile(temp_file_path):
            print("Extracting TAR archive...")
            with tarfile.open(temp_file_path, 'r:*') as tar_ref:
                tar_ref.extractall(target_dir)
        else:
            raise Exception("Unsupported archive format. Provide a ZIP, TAR, or Git repository URL.")
            
        # Flatten structure if the archive extracted all contents into a single nested directory
        subdirs = os.listdir(target_dir)
        if len(subdirs) == 1 and os.path.isdir(os.path.join(target_dir, subdirs[0])):
            nested_dir = os.path.join(target_dir, subdirs[0])
            print(f"Promoting nested directory contents from {subdirs[0]} to root...")
            for item in os.listdir(nested_dir):
                shutil.move(os.path.join(nested_dir, item), os.path.join(target_dir, item))
            os.rmdir(nested_dir)
            
        return "archive"
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def deploy_from_url(config, params):
    """Downloads source code, SCPs to bastion, and initiates webservice restart."""
    logs = []
    
    def log(msg, category="info"):
        logs.append({"message": msg, "category": category})
        print(f"[{category.upper()}] {msg}")
    
    # 1. Read SSH keys from local device
    log("Reading private SSH key from local device...")
    try:
        verify_and_read_ssh_key(config)
        log("Successfully read and verified local private SSH key.")
    except Exception as e:
        log(f"Local SSH key verification failed: {e}", "error")
        return {"success": False, "logs": logs}
        
    # 2. SSH to toolforge (connection check)
    log(f"Connecting to Toolforge bastion ({config['bastion_host']}) via SSH...")
    stdout, stderr, code = run_ssh_command_capture(config, "echo 'ready'")
    if code != 0:
        log(f"SSH bastion connection failed (code {code}): {stderr or stdout}", "error")
        return {"success": False, "logs": logs}
    log("Bastion SSH connection verified successfully.")
    
    # 3. Take the URL from request body, copy/download files locally
    url = params.get("url")
    if not url:
        log("Deployment failed: No 'url' provided in request body.", "error")
        return {"success": False, "logs": logs}
        
    log(f"Taking URL from request body: {url}. Extracting files...")
    local_temp_dir = tempfile.mkdtemp()
    try:
        archive_type = download_source_files(url, local_temp_dir)
        log(f"Files successfully copied/extracted locally (Type: {archive_type}).")
    except Exception as e:
        log(f"Failed to copy files locally: {e}", "error")
        if os.path.exists(local_temp_dir):
            shutil.rmtree(local_temp_dir)
        return {"success": False, "logs": logs}
        
    # 4. Process files and compile deployment scripts
    entry_file = params.get("entry_file", "app.py")
    app_var_name = params.get("app_var_name", "app")
    python_version = params.get("python_version", "python3.11")
    tool_name = config["tool_name"]
    
    log("Preparing deployment scripts...")
    local_entry_path = os.path.join(local_temp_dir, entry_file)
    
    if not os.path.exists(local_entry_path):
        py_files = [f for f in os.listdir(local_temp_dir) if f.endswith(".py")]
        log(f"Warning: Entry file '{entry_file}' not found. Available python files: {py_files}", "warning")
        if len(py_files) == 1:
            log(f"Auto-detecting '{py_files[0]}' as fallback entry file.")
            entry_file = py_files[0]
            local_entry_path = os.path.join(local_temp_dir, entry_file)
            
    module_name = os.path.splitext(entry_file)[0]
    
    # Generate app.py wrapper if it doesn't match standard uWSGI expectations (app.py:app)
    if entry_file != "app.py" or app_var_name != "app":
        log(f"Creating app.py wrapper to map {module_name}:{app_var_name} to app:app...")
        app_wrapper_content = f"""import sys
import os

# Add directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from {module_name} import {app_var_name} as app
except Exception as e:
    print("Error importing Flask application: " + str(e))
    raise e
"""
        with open(os.path.join(local_temp_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write(app_wrapper_content)
            
    # Generate remote deploy.sh script
    deploy_id = str(uuid.uuid4())[:8]
    remote_temp = f"/tmp/tf_deploy_{tool_name}_{deploy_id}"
    
    deploy_sh_content = f"""#!/bin/bash
set -e

echo "Preparing www/python/src directory..."
mkdir -p /data/project/{tool_name}/www/python/src

# Empty www/python/src to prevent old leftover file conflicts
echo "Clearing old code in www/python/src..."
rm -rf /data/project/{tool_name}/www/python/src/* 2>/dev/null || true

echo "Copying new code to www/python/src..."
cp -r {remote_temp}/* /data/project/{tool_name}/www/python/src/
chmod -R 755 /data/project/{tool_name}/www/python/src

# Remove deploy.sh from www/python/src to keep it clean
rm -f /data/project/{tool_name}/www/python/src/deploy.sh

if [ -f "/data/project/{tool_name}/www/python/src/requirements.txt" ]; then
    echo "requirements.txt detected. Checking Python Virtual Environment..."
    echo "Creating virtual environment and installing requirements via a Toolforge Kubernetes Job..."
    
    # Delete old venv first to ensure a clean slate
    rm -rf /data/project/{tool_name}/www/python/venv
    
    # Delete any existing setup-venv job to prevent name collision
    toolforge jobs delete setup-venv 2>/dev/null || true
    
    # Run the setup via a one-off Kubernetes Job with the matching image
    toolforge jobs run setup-venv \\
        --command "/bin/bash -c 'python3 -m venv /data/project/{tool_name}/www/python/venv && /data/project/{tool_name}/www/python/venv/bin/pip install --upgrade pip && /data/project/{tool_name}/www/python/venv/bin/pip install -r /data/project/{tool_name}/www/python/src/requirements.txt'" \\
        --image {python_version} \\
        --wait
        
    # Clean up the job definition after run
    toolforge jobs delete setup-venv
fi

echo "Deploy finished. Web service starting..."
toolforge webservice {python_version} restart || toolforge webservice {python_version} start
"""
    with open(os.path.join(local_temp_dir, "deploy.sh"), "w", encoding="utf-8") as f:
        f.write(deploy_sh_content)
        
    # 5. SSH to Toolforge and copy files (SCP downloaded files to bastion)
    log(f"SSH and copy files: Copying deployment bundle to remote staging folder {remote_temp}...")
    stdout, stderr, code = upload_to_bastion(config, local_temp_dir, remote_temp)
    if code != 0:
        log(f"Failed to copy files to bastion (code {code}): {stderr or stdout}", "error")
        shutil.rmtree(local_temp_dir)
        return {"success": False, "logs": logs}
    log("Files successfully copied to Toolforge staging directory.")
    
    try:
        # 6. Adjust remote staging permissions
        log("Adjusting remote directory permissions...")
        stdout, stderr, code = run_ssh_command_capture(config, f"chmod -R 777 {remote_temp}")
        if code != 0:
            log(f"Failed to adjust remote permissions: {stderr}", "warning")
            
        # 7. Pre-clear old folders to resolve permissions
        log("Resolving permissions by clearing old build directories...")
        clear_cmd = f"rm -rf /data/project/{tool_name}/public_html /data/project/{tool_name}/www/python/src 2>/dev/null || true"
        run_ssh_command_capture(config, clear_cmd)
        
        # 8. Continue deploy as in toolforge_manager.py
        log("Running deployment commands as tool user and restarting webservice...")
        stdout, stderr, code = run_ssh_command_capture(config, f"bash {remote_temp}/deploy.sh", as_tool=True)
        if code != 0:
            log(f"Deployment script failed (code {code}): {stderr or stdout}", "error")
            return {"success": False, "logs": logs}
            
        # Capture remote bash script stdout and write to backend logs
        for line in stdout.splitlines():
            log(line, "remote")
            
        log("Remote deployment execution finished successfully.")
        
        # 9. Clean up remote temp
        log("Cleaning up remote staging folder...")
        run_ssh_command_capture(config, f"rm -rf {remote_temp}")
        log("Remote staging cleaned.")
        
        log(f"★ Flask application deployed successfully! URL: https://{tool_name}.toolforge.org/", "success")
        return {"success": True, "logs": logs, "url": f"https://{tool_name}.toolforge.org/"}
        
    except Exception as e:
        log(f"An unexpected error occurred during deploy process: {e}", "error")
        return {"success": False, "logs": logs}
    finally:
        if os.path.exists(local_temp_dir):
            shutil.rmtree(local_temp_dir)

# --- Flask Endpoints ---

@app.route("/")
def index():
    """Serves a status message for the API."""
    return jsonify({
        "status": "ok",
        "message": "Toolforge Manager API is running",
        "endpoints": [
            {"path": "/api/config", "methods": ["GET", "POST"]},
            {"path": "/api/test-connection", "methods": ["POST"]},
            {"path": "/api/deploy", "methods": ["POST"]},
            {"path": "/api/webservice/status", "methods": ["GET"]},
            {"path": "/api/webservice/control", "methods": ["POST"]}
        ]
    })

@app.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Retrieves current configuration."""
    config = load_config()
    return jsonify(config)

@app.route("/api/config", methods=["POST"])
def save_config_endpoint():
    """Saves/updates configuration."""
    data = request.json or {}
    config = load_config()
    for field in ["username", "tool_name", "ssh_key", "bastion_host"]:
        if field in data:
            config[field] = data[field].strip()
    
    if save_config(config):
        return jsonify({"success": True, "message": "Configuration saved successfully", "config": config})
    return jsonify({"success": False, "message": "Failed to save configuration"}), 500

@app.route("/api/test-connection", methods=["POST"])
def test_connection_endpoint():
    """Validates SSH connection to the Toolforge bastion."""
    config = load_config()
    
    # Check key path and file validity
    try:
        verify_and_read_ssh_key(config)
    except Exception as e:
        return jsonify({"success": False, "message": f"SSH key error: {str(e)}"})
        
    stdout, stderr, code = run_ssh_command_capture(config, "echo 'ready'")
    if code == 0:
        return jsonify({"success": True, "message": "SSH connection verified successfully!"})
    else:
        return jsonify({"success": False, "message": f"SSH connection failed (code {code}): {stderr or stdout}"})

@app.route("/api/deploy", methods=["POST"])
def deploy_endpoint():
    """Endpoint that downloads source code from request URL and deploys to Toolforge."""
    data = request.json or {}
    url = data.get("url")
    if not url:
        return jsonify({"success": False, "message": "Missing 'url' parameter in request body"}), 400
        
    config = load_config()
    
    # Support overriding values from request body
    for field in ["username", "tool_name", "ssh_key", "bastion_host"]:
        if field in data and data[field]:
            config[field] = data[field].strip()
            
    if not config.get("username") or not config.get("tool_name"):
        return jsonify({"success": False, "message": "Wikimedia username and tool name must be configured."}), 400
        
    # Execute pipeline
    result = deploy_from_url(config, data)
    return jsonify(result)

@app.route("/api/webservice/status", methods=["GET"])
def webservice_status():
    """Gets the Toolforge web service status."""
    config = load_config()
    stdout, stderr, code = run_ssh_command_capture(config, "toolforge webservice status", as_tool=True)
    # The webservice status command returns exit code 1 if the webservice is stopped, 
    # so we should treat both stdout and stderr as status output.
    return jsonify({"success": (code == 0), "status": stdout or stderr or "Unknown Status"})

@app.route("/api/webservice/control", methods=["POST"])
def webservice_control():
    """Controls the webservice lifecycle (start, stop, restart)."""
    data = request.json or {}
    action = data.get("action")
    ws_type = data.get("type", "python3.11")
    
    if action not in ["start", "stop", "restart"]:
        return jsonify({"success": False, "message": "Invalid action. Choose 'start', 'stop', or 'restart'."}), 400
        
    config = load_config()
    if action == "start":
        cmd = f"toolforge webservice {ws_type} start"
    elif action == "stop":
        cmd = "toolforge webservice stop"
    else:
        cmd = "toolforge webservice restart"
        
    stdout, stderr, code = run_ssh_command_capture(config, cmd, as_tool=True)
    if code == 0:
        return jsonify({"success": True, "message": f"Webservice {action} succeeded", "output": stdout})
    else:
        return jsonify({"success": False, "message": f"Webservice {action} failed", "error": stderr or stdout})

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Toolforge Manager Backend App")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address to bind the Flask server to")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    
    args = parser.parse_args()
    
    print(f"Starting Toolforge Manager Backend Server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
