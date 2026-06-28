#!/usr/bin/env python3
"""
Wikimedia Toolforge Manager CLI
An interactive and scriptable command-line utility to manage Toolforge tools,
run jobs, control webservices, SSH into the bastion host, and transfer files.
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import uuid
from pathlib import Path
import click

# Try importing readline for better input editing support
try:
    import readline
except ImportError:
    pass

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
            click.secho(f"Error loading config from {config_path}: {e}", fg="red")
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
        click.secho(f"Configuration saved to {config_path}", fg="green")
        return True
    except Exception as e:
        click.secho(f"Error saving config: {e}", fg="red")
        return False

def print_header():
    """Compact header using the Wikimedia ASCII logo + deployr info side by side."""
    _LOGO = [
        "             %%%%%%%%%%%%             ",
        "         %%%%%%%%%%%%%%%%%%%%         ",
        "      %%%%%%%%%%      %%%%%%%%%%      ",
        "    %%%%%%%                %%%%%%%    ",
        "    %%%%%                    %%%%%    ",
        "         %        ##                  ",
        " #          %%% ############        # ",
        " ####      % %% #####            #### ",
        "#####     %%%  % ##              #####",
        "####    ++++++++++++++++++++++*   ####",
        "####    +++++++++++++++++++++     ####",
        "#####     ++++++++++++++++       #####",
        " ####          ++++++++++        #### ",
        " #####      +++++++++++++++     ##### ",
        "  #####     +++++++++++++++    #####  ",
        "   ######                    ######   ",
        "    #######                #######    ",
        "      ##########      ##########      ",
        "         ########    ########         ",
        "             ####    ####             ",
    ]
    _INFO = [
        "",
        "",
        "",
        "",
        click.style("  DEPLOYR", fg="cyan", bold=True),
        click.style("  Toolforge Deployment Suite", fg="white"),
        click.style("  Wikimedia Developer Tools", fg="white"),
        click.style("  v1.1.1", fg="bright_black"),
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]

    def _colour(line):
        out = []
        for ch in line:
            if ch == "%":
                out.append(click.style(ch, fg="yellow", bold=True))
            elif ch == "#":
                out.append(click.style(ch, fg="blue", bold=True))
            elif ch == "+":
                out.append(click.style(ch, fg="cyan", bold=True))
            elif ch == "*":
                out.append(click.style(ch, fg="white", bold=True))
            else:
                out.append(ch)
        return "".join(out)

    click.echo()
    for i, line in enumerate(_LOGO):
        txt = _INFO[i] if i < len(_INFO) else ""
        click.echo(f"  {_colour(line)}{txt}")
    click.echo()

def configure_settings(config):
    """Configures or updates settings."""
    click.secho("\n--- Configure Toolforge CLI Settings ---", fg="cyan", bold=True)
    config["username"] = click.prompt("Wikimedia Username", default=config.get("username", ""))
    config["tool_name"] = click.prompt("Default Tool Name (without 'tools.' prefix)", default=config.get("tool_name", ""))
    
    ssh_key_default = config.get("ssh_key", "")
    config["ssh_key"] = click.prompt("Path to Private SSH Key (blank for default SSH agent)", default=ssh_key_default, show_default=False)
    
    config["bastion_host"] = click.prompt("Bastion Host", default=config.get("bastion_host", "login.toolforge.org"))
    
    save_config(config)
    return config

def check_config(config):
    """Ensures username and tool name are set; configures them if missing."""
    if not config.get("username"):
        click.secho("No Wikimedia username found. Let's configure it first!", fg="yellow")
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
            tool_name = click.prompt("Enter tool name")
            if not tool_name:
                click.secho("Tool name required to run as tool.", fg="red")
                return False
        
        if command:
            # Run specific command inside the tool shell
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
        click.secho("Connecting to Toolforge...", fg="blue")
        if remote_cmd:
            click.secho(f"Executing: {remote_cmd}\n", fg="yellow")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        click.secho(f"\nSSH session exited with error: {e}", fg="red")
        return False
    except KeyboardInterrupt:
        click.secho(f"\nSSH session interrupted.", fg="yellow")
        return True

def run_tool_command_capture(config, command):
    """
    Runs a command on the bastion as the tool, captures and returns stdout/stderr.
    This is used for non-interactive commands where we want to parse or display results in the UI.
    """
    tool_name = config.get("tool_name")
    if not tool_name:
        click.secho("Default tool name is not set!", fg="red")
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

def upload_files(config, local_path=None, dest_path=None):
    """Uploads files/directories to the tool's directory using scp or rsync."""
    tool_name = config.get("tool_name")
    if not tool_name:
        click.secho("Default tool name is not set!", fg="red")
        return
    
    if local_path is None:
        click.secho("\n--- Copy Files to Toolforge ---", fg="cyan", bold=True)
        local_path = click.prompt("Enter local file/directory path to upload", type=click.Path(exists=True))
    
    local_path_expanded = os.path.expanduser(local_path)
    
    if dest_path is None:
        dest_path = click.prompt("Enter destination path relative to tool home (e.g. '.' or 'public_html')", default=".")
    
    click.secho("\nMethod: We will copy to your personal directory first, then move it to the tool's folder.", fg="yellow")
    personal_dest = f"~/tf_transfer_{tool_name}"
    
    scp_cmd = ["scp", "-r"]
    if config.get("ssh_key"):
        scp_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
    
    scp_cmd.extend([local_path_expanded, f"{config['username']}@{config['bastion_host']}:{personal_dest}"])
    
    try:
        click.secho("Uploading to temporary personal storage on bastion...", fg="blue")
        subprocess.run(scp_cmd, check=True)
        
        # Now, run a command on bastion to move/copy it to the tool's folder using sudo
        click.secho(f"Moving files to tool's home folder (/data/project/{tool_name}/{dest_path})...", fg="blue")
        
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
        
        click.secho("Successfully uploaded files to toolforge!", fg="green")
    except Exception as e:
        click.secho(f"File upload failed: {e}", fg="red")

def deploy_flask_app(config, local_flask_path=None, app_var_name=None, local_req_path=None, upload_mode=None, python_version=None):
    """Deploys a local Flask application to Toolforge automatically."""
    tool_name = config.get("tool_name")
    if not tool_name:
        click.secho("Default tool name is not set!", fg="red")
        return

    if local_flask_path is None:
        click.secho("\n--- Deploy Python/Flask Web App ---", fg="cyan", bold=True)
        click.echo("This helper will package your Flask application, generate the required")
        click.echo("WSGI entrypoint ('wsgi.py'), set up a virtual environment on Toolforge,")
        click.echo("install dependencies, and start/restart the Python web service.")
        
        local_flask_path = click.prompt("Enter local Flask app entry file (e.g. app.py, main.py)", type=click.Path(exists=True))

    local_flask_expanded = os.path.expanduser(local_flask_path)
    flask_dir = os.path.dirname(os.path.abspath(local_flask_expanded))

    if app_var_name is None:
        app_var_name = click.prompt("Flask application variable name (inside that file)", default="app")
    
    if local_req_path is None:
        req_default = os.path.join(flask_dir, "requirements.txt")
        if os.path.exists(req_default):
            if click.confirm(f"Found requirements.txt at {req_default}. Use it?", default=True):
                local_req_path = req_default
            else:
                local_req_path = click.prompt("Enter local requirements.txt path (optional, press Enter if none)", default="", show_default=False)
        else:
            local_req_path = click.prompt("Enter local requirements.txt path (optional, press Enter if none)", default="", show_default=False)

    if local_req_path:
        local_req_expanded = os.path.expanduser(local_req_path)
        if not os.path.exists(local_req_expanded):
            click.secho(f"Local requirements file does not exist: {local_req_path}", fg="red")
            return
    else:
        local_req_expanded = ""

    if upload_mode is None:
        click.echo(f"\nDeployment options:")
        click.echo("1. Upload ONLY the Flask entry file")
        click.echo("2. Upload ENTIRE directory containing the file (Recommended for multi-file apps)")
        upload_choice = click.prompt("Choose option", default="2", type=click.Choice(["1", "2"]))
        upload_mode = "dir" if upload_choice == "2" else "file"
    elif upload_mode not in ("dir", "file"):
        click.secho(f"Invalid upload mode: {upload_mode}. Must be 'dir' or 'file'.", fg="red")
        return

    if python_version is None:
        python_version = click.prompt("Target Python runtime version (e.g., python3.11, python3.9)", default="python3.11")

    click.secho("\nPreparing deployment package...", fg="blue")
    
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
            
        # Generate random unique ID for remote temporary directory
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
        with open(os.path.join(temp_dir, "deploy.sh"), "w", encoding="utf-8") as f:
            f.write(deploy_sh_content)

        # SCP local temp dir to remote /tmp
        scp_cmd = ["scp", "-r"]
        if config.get("ssh_key"):
            scp_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
        
        scp_cmd.extend([temp_dir, f"{config['username']}@{config['bastion_host']}:{remote_temp}"])
        
        click.secho("Uploading deployment bundle to remote staging...", fg="blue")
        subprocess.run(scp_cmd, check=True)
        
        # Give permission so tools user can read files inside /tmp folder
        click.secho("Adjusting permissions...", fg="blue")
        chmod_cmd = f"chmod -R 777 {remote_temp}"
        ssh_chmod = get_ssh_cmd_base(config, tty=False)
        ssh_chmod.append(chmod_cmd)
        subprocess.run(ssh_chmod, check=True)
        
        # Clean up old source directories owned by the SSH user first to prevent permission-denied issues
        click.secho("Clearing old application directories using SSH user to resolve folder permissions...", fg="blue")
        clear_cmd = f"rm -rf /data/project/{tool_name}/public_html /data/project/{tool_name}/www/python/src 2>/dev/null || true"
        ssh_clear = get_ssh_cmd_base(config, tty=False)
        ssh_clear.append(clear_cmd)
        subprocess.run(ssh_clear, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        click.secho("Running installation and restarting webservice as tool user...", fg="blue")
        # Run it inside tool's bash
        run_ssh_session(config, f"bash {remote_temp}/deploy.sh", as_tool=True)
        
        # Clean up remote temp
        click.secho("Cleaning up remote staging folder...", fg="blue")
        cleanup_cmd = f"rm -rf {remote_temp}"
        ssh_cleanup = get_ssh_cmd_base(config, tty=False)
        ssh_cleanup.append(cleanup_cmd)
        subprocess.run(ssh_cleanup, check=True)
        
        click.secho(f"\n★ Flask application deployed successfully! ★", fg="green", bold=True)
        click.secho(f"Deployment URL: https://{tool_name}.toolforge.org/", fg="cyan", bold=True)
        
    except Exception as e:
        click.secho(f"\nDeployment failed: {e}", fg="red")
    finally:
        # Clean up local temp folder
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def _draw_box(title, lines, width=54):
    """Draws a Unicode box with a title and content lines."""
    click.secho(f"╔{'═' * width}╗", fg="cyan")
    click.secho(f"║  {click.style(title, bold=True, fg='cyan'):<{width + 9}}║", fg="cyan")
    click.secho(f"╠{'═' * width}╣", fg="cyan")
    for line in lines:
        click.secho(f"║  {line:<{width - 2}}║", fg="cyan")
    click.secho(f"╚{'═' * width}╝", fg="cyan")

def manage_webservice(config):
    """Sub-menu to manage Toolforge web services."""
    tool_name = config.get("tool_name")
    if not tool_name:
        click.secho("Default tool name is not set!", fg="red")
        return

    while True:
        click.clear()
        _draw_box(
            f"Web Service Management  [{tool_name}]",
            [
                click.style(" 1", fg="green", bold=True) + "  View Web Service Status",
                click.style(" 2", fg="green", bold=True) + "  Start Web Service",
                click.style(" 3", fg="red",   bold=True) + "  Stop Web Service",
                click.style(" 4", fg="yellow", bold=True) + "  Restart Web Service",
                click.style(" 5", fg="blue",   bold=True) + "  Deploy Python/Flask Web App",
                "",
                click.style(" 6", bold=True) + "  ← Back to Main Menu",
            ]
        )

        choice = click.prompt("\nChoose an option", default="1", type=click.Choice(["1", "2", "3", "4", "5", "6"]))

        if choice == "1":
            out, err = run_tool_command_capture(config, "toolforge webservice status")
            if out:
                click.secho("\n● Webservice Status", fg="green", bold=True)
                click.echo(out)
            else:
                click.secho(f"\n✗ Error fetching status: {err}", fg="red")
            click.pause(info="\nPress any key to continue...")
        elif choice == "2":
            ws_type = click.prompt("Framework/type (e.g. python3.11, node20, php8.2, buildservice)", default="buildservice")
            click.secho(f"\n▶ Starting '{ws_type}'...", fg="blue")
            run_ssh_session(config, f"toolforge webservice {ws_type} start", as_tool=True)
            click.pause(info="\nPress any key to continue...")
        elif choice == "3":
            if click.confirm(click.style("\n⚠  Are you sure you want to STOP the webservice?", fg="red", bold=True), default=False):
                click.secho("■ Stopping webservice...", fg="red")
                run_ssh_session(config, "toolforge webservice stop", as_tool=True)
                click.pause(info="\nPress any key to continue...")
            else:
                click.secho("Cancelled.", fg="yellow")
        elif choice == "4":
            if click.confirm(click.style("\n↺  Restart the webservice?", fg="yellow", bold=True), default=True):
                click.secho("↺ Restarting webservice...", fg="yellow")
                run_ssh_session(config, "toolforge webservice restart", as_tool=True)
                click.pause(info="\nPress any key to continue...")
        elif choice == "5":
            deploy_flask_app(config)
        elif choice == "6":
            break

def manage_jobs(config):
    """Sub-menu to manage Kubernetes Jobs."""
    tool_name = config.get("tool_name")
    if not tool_name:
        click.secho("Default tool name is not set!", fg="red")
        return

    while True:
        click.clear()
        _draw_box(
            f"Kubernetes Jobs  [{tool_name}]",
            [
                click.style(" 1", fg="green",  bold=True) + "  List Jobs",
                click.style(" 2", fg="blue",   bold=True) + "  Run a New Job (One-off or Scheduled)",
                click.style(" 3", fg="red",    bold=True) + "  Delete a Job",
                click.style(" 4", fg="cyan",   bold=True) + "  View Job Logs",
                "",
                click.style(" 5", bold=True) + "  ← Back to Main Menu",
            ]
        )

        choice = click.prompt("\nChoose an option", default="1", type=click.Choice(["1", "2", "3", "4", "5"]))

        if choice == "1":
            out, err = run_tool_command_capture(config, "toolforge jobs list")
            if out:
                click.secho("\n● Kubernetes Jobs", fg="green", bold=True)
                click.echo_via_pager(out)
            else:
                click.secho(f"\n✗ Error fetching jobs list: {err}", fg="red")
                click.pause(info="\nPress any key to continue...")
        elif choice == "2":
            job_name = click.prompt("\nJob name")
            if not job_name:
                click.secho("Job name is required.", fg="red")
                continue
            command = click.prompt("Command to run (e.g. python3 my_script.py)")
            if not command:
                click.secho("Command is required.", fg="red")
                continue
            image = click.prompt("Container image", default="python3.11")
            schedule = click.prompt("Cron schedule (optional, blank = one-off)", default="", show_default=False)

            run_cmd = f"toolforge jobs run {job_name} --command \"{command}\" --image {image}"
            if schedule:
                run_cmd += f" --schedule \"{schedule}\""

            click.secho(f"\n▶ Submitting job '{job_name}'...", fg="blue")
            run_ssh_session(config, run_cmd, as_tool=True)
            click.pause(info="\nPress any key to continue...")

        elif choice == "3":
            job_name = click.prompt("\nJob name to delete")
            if not job_name:
                continue
            if click.confirm(click.style(f"\n⚠  Permanently delete job '{job_name}'?", fg="red", bold=True), default=False):
                click.secho(f"✗ Deleting job '{job_name}'...", fg="red")
                run_ssh_session(config, f"toolforge jobs delete {job_name}", as_tool=True)
                click.pause(info="\nPress any key to continue...")
            else:
                click.secho("Cancelled.", fg="yellow")

        elif choice == "4":
            job_name = click.prompt("\nJob name to check logs")
            if not job_name:
                continue
            log_choice = click.prompt(
                "Log type",
                default="out",
                type=click.Choice(["out", "err"]),
                show_choices=True
            )
            log_file = f"/data/project/{tool_name}/{job_name}.{log_choice}"
            click.secho(f"\n📄 Fetching {log_file} ...", fg="blue")
            # capture and page the output
            out, err = run_tool_command_capture(
                config,
                f"tail -n 200 {log_file} 2>/dev/null || echo 'No logs found at {log_file}'"
            )
            if out:
                click.echo_via_pager(out)
            else:
                click.secho(f"✗ Could not fetch logs: {err}", fg="red")
                click.pause(info="\nPress any key to continue...")

        elif choice == "5":
            break

def setup_ssh_tunnel(config, local_port=None, remote_host=None, remote_port=None):
    """Establishes an SSH tunnel/port forwarding for database access or similar."""
    click.secho("\n--- Establish Port Forwarding / SSH Tunnel ---", fg="cyan", bold=True)
    click.echo("Toolforge databases are only accessible from within the Toolforge cluster.")
    click.echo("This feature allows you to forward a database or service port to your local machine.")
    
    if local_port is None:
        local_port = click.prompt("Enter Local Port (e.g., 3306 for MySQL, 8080 for web)", default="3306")
    
    if remote_host is None:
        click.echo("\nDatabase Server names depend on the project (e.g. 'enwiki.web.db.svc.wikimedia.cloud' or 'tools.db.svc.wikimedia.cloud')")
        remote_host = click.prompt("Enter Remote Host/IP on Toolforge", default="tools.db.svc.wikimedia.cloud")
        
    if remote_port is None:
        remote_port = click.prompt("Enter Remote Port", default="3306")
    
    # We construct the SSH tunnel command
    ssh_tunnel_cmd = ["ssh", "-N", "-L", f"{local_port}:{remote_host}:{remote_port}"]
    
    if config.get("ssh_key"):
        ssh_tunnel_cmd.extend(["-i", os.path.expanduser(config["ssh_key"])])
    
    ssh_tunnel_cmd.append(f"{config['username']}@{config['bastion_host']}")
    
    click.secho(f"\nStarting tunnel: Local port {local_port} -> {remote_host}:{remote_port}", fg="green")
    click.secho("Press Ctrl+C to terminate the tunnel.", fg="yellow")
    click.secho(f"Command running: {' '.join(ssh_tunnel_cmd)}", fg="blue")
    
    try:
        subprocess.run(ssh_tunnel_cmd, check=True)
    except KeyboardInterrupt:
        click.secho(f"\nSSH Tunnel terminated.", fg="green")
    except Exception as e:
        click.secho(f"\nError establishing SSH Tunnel: {e}", fg="red")

def interactive_console(config):
    """Runs the main interactive loop of the toolforge manager CLI."""
    while True:
        click.clear()
        print_header()

        # ── Status bar ──────────────────────────────────────────────────────
        tool = config.get('tool_name') or click.style('not set', fg='red')
        user = click.style(config['username'], fg='cyan', bold=True)
        host = click.style(config['bastion_host'], fg='yellow')
        click.echo(f"  Tool: {click.style(tool, fg='magenta', bold=True)}   User: {user}   Host: {host}")
        click.echo()

        # ── Main menu box ───────────────────────────────────────────────────
        # NOTE: click.style() injects invisible ANSI bytes that break f-string
        # width formatting. We build each row manually: badge + visible text +
        # explicit spaces to reach column W, then the right border.
        W = 54  # visible inner width

        def _row(badge_styled, badge_visible_len, label, total_inner=W):
            # total_inner = 2 (left pad) + badge_visible_len + 1 (space) + label + padding + 0 (right border handled outside)
            used = 2 + badge_visible_len + 1 + len(label)
            pad = total_inner - used
            return f"║  {badge_styled} {label}{' ' * pad}║"

        click.secho(f"╔{'═' * W}╗", fg="cyan")
        click.secho(f"║{'  ── SSH & Shell':^{W}}║", fg="cyan")
        click.secho(f"╠{'═' * W}╣", fg="cyan")
        click.secho(_row(click.style(' 1 ', fg='black', bg='green'),  3, "SSH to Bastion (Interactive)"), fg="cyan")
        click.secho(_row(click.style(' 2 ', fg='black', bg='green'),  3, "Switch to Tool Shell (become)"), fg="cyan")
        click.secho(f"╠{'═' * W}╣", fg="cyan")
        click.secho(f"║{'  ── Manage':^{W}}║", fg="cyan")
        click.secho(f"╠{'═' * W}╣", fg="cyan")
        click.secho(_row(click.style(' 3 ', fg='black', bg='cyan'),   3, "Web Service Control"), fg="cyan")
        click.secho(_row(click.style(' 4 ', fg='black', bg='cyan'),   3, "Kubernetes Jobs"), fg="cyan")
        click.secho(_row(click.style(' 5 ', fg='black', bg='cyan'),   3, "Upload Files / Deploy Code"), fg="cyan")
        click.secho(_row(click.style(' 6 ', fg='black', bg='cyan'),   3, "SSH Database Tunnel"), fg="cyan")
        click.secho(f"╠{'═' * W}╣", fg="cyan")
        click.secho(_row(click.style(' 7 ', fg='black', bg='white'),  3, "Settings"), fg="cyan")
        click.secho(_row(click.style(' 8 ', fg='black', bg='red'),    3, "Exit"), fg="cyan")
        click.secho(f"╚{'═' * W}╝", fg="cyan")

        choice = click.prompt("\n  Choose", default="1", type=click.Choice(["1","2","3","4","5","6","7","8"]))

        if choice == "1":
            run_ssh_session(config)
        elif choice == "2":
            run_ssh_session(config, as_tool=True)
        elif choice == "3":
            manage_webservice(config)
        elif choice == "4":
            manage_jobs(config)
        elif choice == "5":
            click.clear()
            click.secho("\n  Upload / Deploy", fg="cyan", bold=True)
            click.echo("  1. Copy arbitrary files/directories (scp)")
            click.echo("  2. Deploy a Python/Flask Web App (guided)")
            deploy_choice = click.prompt("  Choose", default="2", type=click.Choice(["1", "2"]))
            if deploy_choice == "1":
                upload_files(config)
            else:
                deploy_flask_app(config)
        elif choice == "6":
            setup_ssh_tunnel(config)
        elif choice == "7":
            config = configure_settings(config)
        elif choice == "8":
            click.secho("\nThank you for using Deployr. Goodbye!\n", fg="green")
            break

# ── CLICK COMMAND LINE INTERFACE DEFINITION ──────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Deployr - Interactive and scriptable management suite for Wikimedia Toolforge."""
    if ctx.invoked_subcommand is None:
        config = load_config()
        config = check_config(config)
        interactive_console(config)


@cli.command("ssh")
def cli_ssh():
    """Connect directly to the Toolforge bastion server."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config)

@cli.command("shell")
def cli_shell():
    """Switch context directly to your tool's bash shell (become)."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config, as_tool=True)

@cli.group("webservice")
def cli_webservice():
    """Manage and deploy web services on Toolforge."""
    pass

@cli_webservice.command("status")
def cli_ws_status():
    """Get the current running status of the webservice."""
    config = load_config()
    config = check_config(config)
    out, err = run_tool_command_capture(config, "toolforge webservice status")
    if out:
        click.secho(f"\n{out}", fg="green")
    else:
        click.secho(f"\nError: {err}", fg="red")

@cli_webservice.command("start")
@click.option("--type", "-t", default="buildservice", help="Webservice framework type (e.g. python3.11, php8.2, buildservice).")
def cli_ws_start(type):
    """Start the webservice on Toolforge."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config, f"toolforge webservice {type} start", as_tool=True)

@cli_webservice.command("stop")
def cli_ws_stop():
    """Stop the running webservice on Toolforge."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config, "toolforge webservice stop", as_tool=True)

@cli_webservice.command("restart")
def cli_ws_restart():
    """Restart the webservice on Toolforge."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config, "toolforge webservice restart", as_tool=True)

@cli_webservice.command("deploy")
@click.argument("entry_file", type=click.Path(exists=True))
@click.option("--app-var", default="app", help="Flask app variable name (e.g. app, myapp)")
@click.option("--requirements", type=click.Path(exists=True), help="Path to local requirements.txt file")
@click.option("--mode", type=click.Choice(["dir", "file"]), default="dir", help="Upload a single file or the whole directory")
@click.option("--python", default="python3.11", help="Target Toolforge Python version (e.g. python3.11, python3.9)")
def cli_ws_deploy(entry_file, app_var, requirements, mode, python):
    """Deploy a Flask application to Toolforge automatically."""
    config = load_config()
    config = check_config(config)
    deploy_flask_app(config, entry_file, app_var, requirements, mode, python)

@cli.group("jobs")
def cli_jobs():
    """Manage Kubernetes jobs running under the tool account."""
    pass

@cli_jobs.command("list")
def cli_jobs_list():
    """List all scheduled and continuous jobs."""
    config = load_config()
    config = check_config(config)
    out, err = run_tool_command_capture(config, "toolforge jobs list")
    if out:
        click.secho(f"\n{out}", fg="green")
    else:
        click.secho(f"\nError: {err}", fg="red")

@cli_jobs.command("run")
@click.argument("name")
@click.argument("command")
@click.option("--image", default="python3.11", help="Image tag to run under")
@click.option("--schedule", help="Cron schedule expression (optional)")
def cli_jobs_run(name, command, image, schedule):
    """Run a new Kubernetes job on the cluster."""
    config = load_config()
    config = check_config(config)
    run_cmd = f"toolforge jobs run {name} --command \"{command}\" --image {image}"
    if schedule:
        run_cmd += f" --schedule \"{schedule}\""
    run_ssh_session(config, run_cmd, as_tool=True)

@cli_jobs.command("delete")
@click.argument("name")
def cli_jobs_delete(name):
    """Delete a running or scheduled Kubernetes job."""
    config = load_config()
    config = check_config(config)
    run_ssh_session(config, f"toolforge jobs delete {name}", as_tool=True)

@cli_jobs.command("logs")
@click.argument("name")
@click.option("--err", is_flag=True, help="Fetch standard error (.err) log instead of standard out")
def cli_jobs_logs(name, err):
    """Tail the logs of a Kubernetes job (shows last 50 lines)."""
    config = load_config()
    config = check_config(config)
    suffix = "err" if err else "out"
    log_file = f"/data/project/{config['tool_name']}/{name}.{suffix}"
    run_ssh_session(config, f"tail -n 50 {log_file} 2>/dev/null || echo 'No logs found at {log_file}'", as_tool=True)

@cli.command("upload")
@click.argument("local_path", type=click.Path(exists=True))
@click.argument("dest_path", default=".")
def cli_upload(local_path, dest_path):
    """Upload a file or directory to Toolforge."""
    config = load_config()
    config = check_config(config)
    upload_files(config, local_path, dest_path)

@cli.command("tunnel")
@click.option("--local-port", "-l", default="3306", help="Local port to bind to")
@click.option("--remote-host", "-h", default="tools.db.svc.wikimedia.cloud", help="Remote Wikimedia service host name")
@click.option("--remote-port", "-r", default="3306", help="Remote port of the service")
def cli_tunnel(local_port, remote_host, remote_port):
    """Open an SSH tunnel to query Wikimedia database servers locally."""
    config = load_config()
    config = check_config(config)
    setup_ssh_tunnel(config, local_port, remote_host, remote_port)

@cli.command("configure")
def cli_configure():
    """Configure your Wikimedia developer credentials."""
    config = load_config()
    configure_settings(config)

if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        click.secho(f"\n\nCLI terminated by user. Goodbye!\n", fg="yellow")
        sys.exit(0)
