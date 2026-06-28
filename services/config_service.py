import os
import json
from pathlib import Path

CONFIG_FILE_NAME = ".toolforge_config.json"
DEFAULT_BASTION_HOST = "login.toolforge.org"


def get_config_path():
    return Path.home() / CONFIG_FILE_NAME


def load_config():
    """Load config from file, falling back to env vars and then defaults."""
    config_path = get_config_path()
    config = {
        "username": "",
        "tool_name": "",
        "ssh_key": os.environ.get("TOOLFORGE_SSH_KEY", ""),
        "bastion_host": os.environ.get("TOOLFORGE_BASTION_HOST", DEFAULT_BASTION_HOST),
    }
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update({k: v for k, v in saved.items() if v})
        except Exception as e:
            print(f"Error loading config from {config_path}: {e}")
    return config


def save_config(config):
    """Save configuration to the user's home directory."""
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def build_config(data: dict) -> dict:
    """Builds the runtime config from the request body and environment.

    Per-request, user-specific values (``username``, ``tool_name``) come from
    the frontend request body. Host/infra values (``bastion_host``, the SSH key
    path) come from the environment (.env). The returned dict keeps the shape
    the SSH and deploy services already expect.
    """
    data = data or {}
    return {
        "username": (data.get("username") or "").strip(),
        "tool_name": (data.get("tool_name") or "").strip(),
        "bastion_host": os.environ.get("TOOLFORGE_BASTION_HOST", DEFAULT_BASTION_HOST),
        "ssh_key": os.environ.get("TOOLFORGE_SSH_KEY", ""),
    }


def validate_config(config: dict, required: tuple = ("username", "tool_name")) -> list:
    """Returns the list of required fields missing (empty/blank) from config."""
    return [field for field in required if not config.get(field)]


def verify_and_read_ssh_key(config: dict) -> str:
    """Reads the SSH private key from the local device to verify access and format."""
    ssh_key_path = os.path.expanduser(config.get("ssh_key", ""))
    if not ssh_key_path:
        raise Exception("SSH key path is not configured. Set TOOLFORGE_SSH_KEY in .env.")
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
