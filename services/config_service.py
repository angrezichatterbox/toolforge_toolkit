import os
import json
from pathlib import Path

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
