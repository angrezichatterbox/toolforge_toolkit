from flask import Blueprint, request, jsonify
from services.config_service import load_config, save_config, verify_and_read_ssh_key
from services.ssh_service import run_ssh_command_capture

config_bp = Blueprint('config', __name__)

@config_bp.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Retrieves current configuration."""
    config = load_config()
    return jsonify(config)

@config_bp.route("/api/config", methods=["POST"])
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

@config_bp.route("/api/test-connection", methods=["POST"])
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
