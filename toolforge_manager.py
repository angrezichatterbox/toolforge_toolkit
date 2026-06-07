#!/usr/bin/env python3
"""
Wikimedia Toolforge Manager CLI
An interactive command-line utility to manage Toolforge tools, run jobs,
control webservices, SSH into the bastion host, and transfer files.
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import uuid
from pathlib import Path

# Try importing readline for better input editing support
try:
    import readline
except ImportError:
    pass

# ANSI Color Codes
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
BLUE = "\033[34m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"

CONFIG_FILE_NAME = ".toolforge_config.json"

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
            print(f"{RED}Error loading config from {config_path}: {e}{RESET}")
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
        print(f"{GREEN}Configuration saved to {config_path}{RESET}")
        return True
    except Exception as e:
        print(f"{RED}Error saving config: {e}{RESET}")
        return False

def print_header():
    """Prints a beautiful CLI header."""
    print("\n" + "=" * 65)
    print(f"{BOLD}{CYAN}    ____             __                                          {RESET}")
    print(f"{BOLD}{CYAN}   / __ \\___  ____  / /___  __  ______                           {RESET}")
    print(f"{BOLD}{CYAN}  / / / / _ \\/ __ \\/ / __ \\/ / / / ___/                          {RESET}")
    print(f"{BOLD}{CYAN} / /_/ /  __/ /_/ / / /_/ / /_/ / /                              {RESET}")
    print(f"{BOLD}{CYAN}/_____/\\___/ .___/_/\\____/\\__, /_/                               {RESET}")
    print(f"{BOLD}{CYAN}          /_/            /____/                                  {RESET}")
    print(f"{BOLD}{BLUE}               Deployr - Toolforge Deployment Suite v1.0.0       {RESET}")
    print("=" * 65 + "\n")

def get_input(prompt, default=""):
    """Gets user input with a prompt and an optional default value."""
    prompt_str = f"{prompt} [{default}]: " if default else f"{prompt}: "
    val = input(prompt_str).strip()
    return val if val else default

def configure_settings(config):
    """Configures or updates settings."""
    print(f"\n{BOLD}{CYAN}--- Configure Toolforge CLI Settings ---{RESET}")
    config["username"] = get_input("Wikimedia Username", config.get("username", ""))
    config["tool_name"] = get_input("Default Tool Name (without 'tools.' prefix)", config.get("tool_name", ""))
    
    ssh_key_default = config.get("ssh_key", "")
    config["ssh_key"] = get_input("Path to Private SSH Key (blank for default SSH agent)", ssh_key_default)
    
    config["bastion_host"] = get_input("Bastion Host", config.get("bastion_host", "login.toolforge.org"))
    
    save_config(config)
    return config

def check_config(config):
    """Ensures username and tool name are set; configures them if missing."""
    if not config.get("username"):
        print(f"{YELLOW}No Wikimedia username found. Let's configure it first!{RESET}")
        config = configure_settings(config)
    return config

def get_ssh_cmd_base(config, tty=False):
    """Constructs the base SSH command list."""
    cmd = ["ssh"]
    if tty:
        cmd.append("-t")
    if config.get("ssh_key"):
        cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
    
    username = config["username"]
    host = config["bastion_host"]
    cmd.append(f"{username}@{host}")
    return cmd

def run_ssh_session(config, command=None, as_tool=False):
    """
    Runs an interactive or non-interactive SSH session.
    If command is provided, executes that command.
    If as_tool is True, runs 'become <tool>' first.
    """
    cmd = get_ssh_cmd_base(config, tty=True)
    
    # Target command building
    remote_cmd = ""
    if as_tool:
        tool_name = config.get("tool_name")
        if not tool_name:
            tool_name = get_input("Enter tool name")
            if not tool_name:
                print(f"{RED}Tool name required to run as tool.{RESET}")
                return False
        
        if command:
            # Run specific command inside the tool shell
            # Note: we use sudo -i -u tools.<tool> to execute specific commands non-interactively/interactively
            remote_cmd = f"sudo -i -u tools.{tool_name} {command}"
        else:
            # Drop into tool bash shell
            remote_cmd = f"become {tool_name}"
    else:
        if command:
            remote_cmd = command

    if remote_cmd:
        cmd.append(remote_cmd)

    try:
        print(f"{BLUE}Connecting to Toolforge...{RESET}")
        if remote_cmd:
            print(f"{YELLOW}Executing: {remote_cmd}{RESET}\n")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n{RED}SSH session exited with error: {e}{RESET}")
        return False
    except KeyboardInterrupt:
        print(f"\n{YELLOW}SSH session interrupted.{RESET}")
        return True

def run_tool_command_capture(config, command):
    """
    Runs a command on the bastion as the tool, captures and returns stdout/stderr.
    This is used for non-interactive commands where we want to parse or display results in the UI.
    """
    tool_name = config.get("tool_name")
    if not tool_name:
        print(f"{RED}Default tool name is not set!{RESET}")
        return None, "No tool name configured"
    
    # We construct a base SSH command without allocating a tty to safely capture output
    ssh_base = get_ssh_cmd_base(config, tty=False)
    
    # Execute command inside the tool context using sudo
    remote_cmd = f"sudo -i -u tools.{tool_name} {command}"
    ssh_base.append(remote_cmd)
    
    try:
        result = subprocess.run(ssh_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return None, e.stderr or e.stdout or str(e)

def upload_files(config):
    """Uploads files/directories to the tool's directory using scp or rsync."""
    tool_name = config.get("tool_name")
    if not tool_name:
        print(f"{RED}Default tool name is not set!{RESET}")
        return
    
    print(f"\n{BOLD}{CYAN}--- Copy Files to Toolforge ---{RESET}")
    local_path = get_input("Enter local file/directory path to upload").strip()
    if not local_path:
        print(f"{YELLOW}Operation cancelled.{RESET}")
        return
    
    local_path_expanded = os.path.expanduser(local_path)
    if not os.path.exists(local_path_expanded):
        print(f"{RED}Local path does not exist: {local_path}{RESET}")
        return
    
    # Destination in Toolforge: Tool's home folder is /data/project/<tool_name>
    dest_path = get_input("Enter destination path relative to tool home (e.g. '.' or 'public_html')", ".")
    
    # Build scp command
    # Toolforge bastion doesn't allow direct SCP directly as the tool account easily without passing through
    # your user account first, or you can write to a temporary location in /tmp, or use rsync with sudo.
    # A standard way: upload to your personal home directory, then move it to the tool directory.
    # Alternatively, SCP directly to your user folder: /home/<username>
    
    print(f"\n{YELLOW}Method: We will copy to your personal directory first, then move it to the tool's folder.{RESET}")
    personal_dest = f"~/tf_transfer_{tool_name}"
    
    scp_cmd = ["scp", "-r"]
    if config.get("ssh_key"):
        scp_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
    
    scp_cmd.extend([local_path_expanded, f"{config['username']}@{config['bastion_host']}:{personal_dest}"])
    
    try:
        print(f"{BLUE}Uploading to temporary personal storage on bastion...{RESET}")
        subprocess.run(scp_cmd, check=True)
        
        # Now, run a command on bastion to move/copy it to the tool's folder using sudo
        print(f"{BLUE}Moving files to tool's home folder (/data/project/{tool_name}/{dest_path})...{RESET}")
        
        # Clean destination path if it's '.'
        remote_dest = f"/data/project/{tool_name}/{dest_path if dest_path != '.' else ''}"
        
        # We run ssh to copy files from user home to tools folder
        move_cmd = (
            f"sudo -u tools.{tool_name} mkdir -p {remote_dest} && "
            f"sudo -u tools.{tool_name} cp -r {personal_dest}/* {remote_dest}/ 2>/dev/null || "
            f"sudo -u tools.{tool_name} cp -r {personal_dest} {remote_dest}/ && "
            f"rm -rf {personal_dest}"
        )
        
        ssh_cmd = get_ssh_cmd_base(config, tty=False)
        ssh_cmd.append(move_cmd)
        subprocess.run(ssh_cmd, check=True)
        
        print(f"{GREEN}Successfully uploaded files to toolforge!{RESET}")
    except Exception as e:
        print(f"{RED}File upload failed: {e}{RESET}")

def deploy_flask_app(config):
    """Deploys a local Flask application to Toolforge automatically."""
    tool_name = config.get("tool_name")
    if not tool_name:
        print(f"{RED}Default tool name is not set!{RESET}")
        return

    print(f"\n{BOLD}{CYAN}--- Deploy Python/Flask Web App ---{RESET}")
    print("This helper will package your Flask application, generate the required")
    print("WSGI entrypoint ('wsgi.py'), set up a virtual environment on Toolforge,")
    print("install dependencies, and start/restart the Python web service.")
    
    local_flask_path = get_input("Enter local Flask app entry file (e.g. app.py, main.py)").strip()
    if not local_flask_path:
        print(f"{YELLOW}Operation cancelled.{RESET}")
        return

    local_flask_expanded = os.path.expanduser(local_flask_path)
    if not os.path.exists(local_flask_expanded):
        print(f"{RED}Local file does not exist: {local_flask_path}{RESET}")
        return

    app_var_name = get_input("Flask application variable name (inside that file)", "app")
    
    # Try to auto-detect requirements.txt in the same folder
    flask_dir = os.path.dirname(os.path.abspath(local_flask_expanded))
    req_default = os.path.join(flask_dir, "requirements.txt")
    if os.path.exists(req_default):
        local_req_path = get_input("Enter local requirements.txt path (found matching one!)", req_default)
    else:
        local_req_path = get_input("Enter local requirements.txt path (optional, press Enter if none)", "")

    if local_req_path:
        local_req_expanded = os.path.expanduser(local_req_path)
        if not os.path.exists(local_req_expanded):
            print(f"{RED}Local requirements file does not exist: {local_req_path}{RESET}")
            return
    else:
        local_req_expanded = ""

    print(f"\n{BOLD}Deployment options:{RESET}")
    print("1. Upload ONLY the Flask entry file")
    print("2. Upload ENTIRE directory containing the file (Recommended for multi-file apps)")
    upload_choice = get_input("Choose option", "2")
    upload_mode = "dir" if upload_choice == "2" else "file"

    python_version = get_input("Target Python runtime version (e.g., python3.11, python3.9)", "python3.11")

    print(f"\n{BLUE}Preparing deployment package...{RESET}")
    
    # Create local temporary directory
    temp_dir = tempfile.mkdtemp()
    flask_file_name = os.path.basename(local_flask_expanded)
    module_name = os.path.splitext(flask_file_name)[0]
    
    try:
        if upload_mode == "dir":
            src_dir = os.path.dirname(os.path.abspath(local_flask_expanded))
            
            def ignore_patterns(path, names):
                ignored = []
                for name in names:
                    if name in ('__pycache__', '.git', '.venv', 'venv', 'node_modules') or name.endswith('.pyc'):
                        ignored.append(name)
                return ignored
            
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(temp_dir, item)
                if os.path.isdir(s):
                    if item not in ('__pycache__', '.git', '.venv', 'venv', 'node_modules'):
                        shutil.copytree(s, d, ignore=ignore_patterns)
                else:
                    if not item.endswith('.pyc'):
                        shutil.copy2(s, d)
        else:
            shutil.copy2(local_flask_expanded, os.path.join(temp_dir, flask_file_name))
            
        # Copy requirements.txt to temp_dir if provided explicitly or found during dir copy
        if local_req_expanded and not os.path.exists(os.path.join(temp_dir, "requirements.txt")):
            shutil.copy2(local_req_expanded, os.path.join(temp_dir, "requirements.txt"))
            
        # If the flask app file is not app.py or the app variable is not app,
        # we generate a wrapper app.py so that uWSGI can find it natively.
        if flask_file_name != "app.py" or app_var_name != "app":
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
            with open(os.path.join(temp_dir, "app.py"), "w", encoding="utf-8") as f:
                f.write(app_wrapper_content)
            
        # Generate random unique ID for remote temp directory
        deploy_id = str(uuid.uuid4())[:8]
        remote_temp = f"/tmp/tf_deploy_{tool_name}_{deploy_id}"
        
        # Generate the deploy.sh script inside the temporary directory
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
    echo "This ensures we match the exact {python_version} environment of your web service."
    
    # Delete old venv first to ensure a clean slate
    rm -rf /data/project/{tool_name}/www/python/venv
    
    # Delete any existing setup-venv job to prevent name collision
    toolforge jobs delete setup-venv 2>/dev/null || true
    
    # Run the setup via a one-off Kubernetes Job with the matching image
    toolforge jobs run setup-venv \
        --command "/bin/bash -c 'python3 -m venv /data/project/{tool_name}/www/python/venv && /data/project/{tool_name}/www/python/venv/bin/pip install --upgrade pip && /data/project/{tool_name}/www/python/venv/bin/pip install -r /data/project/{tool_name}/www/python/src/requirements.txt'" \
        --image {python_version} \
        --wait
        
    # Clean up the job definition after run
    toolforge jobs delete setup-venv
fi

echo "Deploy finished. Web service starting..."
toolforge webservice {python_version} restart || toolforge webservice {python_version} start
"""
        with open(os.path.join(temp_dir, "deploy.sh"), "w", encoding="utf-8") as f:
            f.write(deploy_sh_content)

        # SCP local temp dir to remote /tmp
        scp_cmd = ["scp", "-r"]
        if config.get("ssh_key"):
            scp_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
        
        scp_cmd.extend([temp_dir, f"{config['username']}@{config['bastion_host']}:{remote_temp}"])
        
        print(f"{BLUE}Uploading deployment bundle to remote staging...{RESET}")
        subprocess.run(scp_cmd, check=True)
        
        # Give permission so tools user can read files inside /tmp folder
        print(f"{BLUE}Adjusting permissions...{RESET}")
        chmod_cmd = f"chmod -R 777 {remote_temp}"
        ssh_chmod = get_ssh_cmd_base(config, tty=False)
        ssh_chmod.append(chmod_cmd)
        subprocess.run(ssh_chmod, check=True)
        
        # Clean up old source directories owned by the SSH user first to prevent permission-denied issues
        print(f"{BLUE}Clearing old application directories using SSH user to resolve folder permissions...{RESET}")
        clear_cmd = f"rm -rf /data/project/{tool_name}/public_html /data/project/{tool_name}/www/python/src 2>/dev/null || true"
        ssh_clear = get_ssh_cmd_base(config, tty=False)
        ssh_clear.append(clear_cmd)
        subprocess.run(ssh_clear, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"{BLUE}Running installation and restarting webservice as tool user...{RESET}")
        # Run it inside tool's bash
        run_ssh_session(config, f"bash {remote_temp}/deploy.sh", as_tool=True)
        
        # Clean up remote temp
        print(f"{BLUE}Cleaning up remote staging folder...{RESET}")
        cleanup_cmd = f"rm -rf {remote_temp}"
        ssh_cleanup = get_ssh_cmd_base(config, tty=False)
        ssh_cleanup.append(cleanup_cmd)
        subprocess.run(ssh_cleanup, check=True)
        
        print(f"\n{BOLD}{GREEN}★ Flask application deployed successfully! ★{RESET}")
        print(f"{BOLD}{CYAN}Deployment URL: https://{tool_name}.toolforge.org/{RESET}")
        
    except Exception as e:
        print(f"\n{RED}Deployment failed: {e}{RESET}")
    finally:
        # Clean up local temp folder
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def manage_webservice(config):
    """Sub-menu to manage Toolforge web services."""
    tool_name = config.get("tool_name")
    if not tool_name:
        print(f"{RED}Default tool name is not set!{RESET}")
        return

    while True:
        print(f"\n{BOLD}{CYAN}--- Web Service Management ({tool_name}) ---{RESET}")
        print("1. View Web Service Status")
        print("2. Start Web Service")
        print("3. Stop Web Service")
        print("4. Restart Web Service")
        print("5. Deploy Python/Flask Web App")
        print("6. Back to Main Menu")
        
        choice = get_input("Choose an option", "1")
        
        if choice == "1":
            out, err = run_tool_command_capture(config, "toolforge webservice status")
            if out:
                print(f"\n{GREEN}Webservice Status:{RESET}\n{out}")
            else:
                print(f"\n{RED}Error fetching status: {err}{RESET}")
        elif choice == "2":
            ws_type = get_input("Enter framework/type (e.g. python3.11, node20, php8.2, buildservice)", "buildservice")
            print(f"{BLUE}Starting webservice of type '{ws_type}'...{RESET}")
            run_ssh_session(config, f"toolforge webservice {ws_type} start", as_tool=True)
        elif choice == "3":
            print(f"{BLUE}Stopping webservice...{RESET}")
            run_ssh_session(config, "toolforge webservice stop", as_tool=True)
        elif choice == "4":
            print(f"{BLUE}Restarting webservice...{RESET}")
            run_ssh_session(config, "toolforge webservice restart", as_tool=True)
        elif choice == "5":
            deploy_flask_app(config)
        elif choice == "6":
            break
        else:
            print(f"{RED}Invalid option!{RESET}")

def manage_jobs(config):
    """Sub-menu to manage Kubernetes Jobs."""
    tool_name = config.get("tool_name")
    if not tool_name:
        print(f"{RED}Default tool name is not set!{RESET}")
        return

    while True:
        print(f"\n{BOLD}{CYAN}--- Kubernetes Jobs Management ({tool_name}) ---{RESET}")
        print("1. List Jobs")
        print("2. Run a New Job (One-off or Scheduled)")
        print("3. Delete a Job")
        print("4. View Job Logs")
        print("5. Back to Main Menu")
        
        choice = get_input("Choose an option", "1")
        
        if choice == "1":
            out, err = run_tool_command_capture(config, "toolforge jobs list")
            if out:
                print(f"\n{GREEN}Kubernetes Jobs:{RESET}\n{out}")
            else:
                print(f"\n{RED}Error fetching jobs list: {err}{RESET}")
        elif choice == "2":
            job_name = get_input("Enter job name")
            if not job_name:
                print(f"{RED}Job name is required.{RESET}")
                continue
            command = get_input("Enter command to execute (e.g. python3 my_script.py)")
            if not command:
                print(f"{RED}Command is required.{RESET}")
                continue
            image = get_input("Enter container image (e.g. python3.11, node20, latest)", "python3.11")
            schedule = get_input("Enter cron schedule (optional, e.g. '0 0 * * *' for daily, or blank for continuous/one-off)", "")
            
            run_cmd = f"toolforge jobs run {job_name} --command \"{command}\" --image {image}"
            if schedule:
                run_cmd += f" --schedule \"{schedule}\""
            
            print(f"{BLUE}Submitting job '{job_name}'...{RESET}")
            run_ssh_session(config, run_cmd, as_tool=True)
            
        elif choice == "3":
            job_name = get_input("Enter job name to delete")
            if not job_name:
                continue
            print(f"{BLUE}Deleting job '{job_name}'...{RESET}")
            run_ssh_session(config, f"toolforge jobs delete {job_name}", as_tool=True)
            
        elif choice == "4":
            job_name = get_input("Enter job name to check logs")
            if not job_name:
                continue
            # Toolforge stores logs in home folder: <job_name>.out and <job_name>.err
            print(f"\n{BOLD}Select log type:{RESET}")
            print("1. Standard Output (.out)")
            print("2. Standard Error (.err)")
            log_type = get_input("Choose type", "1")
            
            suffix = "out" if log_type == "1" else "err"
            log_file = f"/data/project/{tool_name}/{job_name}.{suffix}"
            
            print(f"{BLUE}Fetching logs from {log_file} (showing last 50 lines)...{RESET}\n")
            run_ssh_session(config, f"tail -n 50 {log_file} 2>/dev/null || echo 'No logs found at {log_file}'", as_tool=True)
            
        elif choice == "5":
            break
        else:
            print(f"{RED}Invalid option!{RESET}")

def setup_ssh_tunnel(config):
    """Establishes an SSH tunnel/port forwarding for database access or similar."""
    print(f"\n{BOLD}{CYAN}--- Establish Port Forwarding / SSH Tunnel ---{RESET}")
    print("Toolforge databases are only accessible from within the Toolforge cluster.")
    print("This feature allows you to forward a database or service port to your local machine.")
    
    local_port = get_input("Enter Local Port (e.g., 3306 for MySQL, 8080 for web)", "3306")
    
    print("\nDatabase Server names depend on the project (e.g. 'enwiki.web.db.svc.wikimedia.cloud' or 'tools.db.svc.wikimedia.cloud')")
    remote_host = get_input("Enter Remote Host/IP on Toolforge", "tools.db.svc.wikimedia.cloud")
    remote_port = get_input("Enter Remote Port", "3306")
    
    # We construct the SSH tunnel command
    # ssh -N -L local_port:remote_host:remote_port user@login.toolforge.org
    ssh_tunnel_cmd = ["ssh", "-N", "-L", f"{local_port}:{remote_host}:{remote_port}"]
    
    if config.get("ssh_key"):
        ssh_tunnel_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
    
    ssh_tunnel_cmd.append(f"{config['username']}@{config['bastion_host']}")
    
    print(f"\n{GREEN}Starting tunnel: Local port {local_port} -> {remote_host}:{remote_port}{RESET}")
    print(f"{YELLOW}Press Ctrl+C to terminate the tunnel.{RESET}")
    print(f"Command running: {' '.join(ssh_tunnel_cmd)}")
    
    try:
        subprocess.run(ssh_tunnel_cmd, check=True)
    except KeyboardInterrupt:
        print(f"\n{GREEN}SSH Tunnel terminated.{RESET}")
    except Exception as e:
        print(f"\n{RED}Error establishing SSH Tunnel: {e}{RESET}")

def main():
    """Main execution loop of the toolforge manager CLI."""
    config = load_config()
    print_header()
    
    # Make sure basic config is available
    config = check_config(config)
    
    while True:
        print(f"\n{BOLD}{CYAN}=== DEPLOYR CONSOLE ({config.get('tool_name') or 'No tool set'}) ==={RESET}")
        print(f"User: {BOLD}{config['username']}{RESET} | Bastion: {BOLD}{config['bastion_host']}{RESET}")
        print("-" * 50)
        print(f"{GREEN}1. SSH to Bastion (Interactive){RESET}")
        print(f"{GREEN}2. Switch to Tool Shell (become <tool>){RESET}")
        print("-" * 50)
        print("3. Web Service Control Menu")
        print("4. Kubernetes Jobs Menu")
        print("5. Upload Files / Deploy Code (scp/rsync)")
        print("6. SSH Port Forwarding / Database Tunnel")
        print("-" * 50)
        print("7. Settings / Configure tool & credentials")
        print("8. Exit")
        print("=" * 50)
        
        choice = get_input("Choose an option", "1")
        
        if choice == "1":
            run_ssh_session(config)
        elif choice == "2":
            run_ssh_session(config, as_tool=True)
        elif choice == "3":
            manage_webservice(config)
        elif choice == "4":
            manage_jobs(config)
        elif choice == "5":
            upload_files(config)
        elif choice == "6":
            setup_ssh_tunnel(config)
        elif choice == "7":
            config = configure_settings(config)
        elif choice == "8":
            print(f"\n{GREEN}Thank you for using Deployr. Goodbye!{RESET}\n")
            break
        else:
            print(f"{RED}Invalid option, please try again.{RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}CLI terminated by user. Goodbye!{RESET}\n")
        sys.exit(0)
