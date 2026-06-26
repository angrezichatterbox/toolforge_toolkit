import os
import subprocess

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
