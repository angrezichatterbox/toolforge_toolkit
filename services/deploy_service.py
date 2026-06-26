import os
import shutil
import tempfile
import uuid
from .config_service import verify_and_read_ssh_key
from .ssh_service import run_ssh_command_capture, upload_to_bastion
from .download_service import download_source_files

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
