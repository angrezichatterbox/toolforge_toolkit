from flask import Blueprint, request, jsonify
from services.config_service import build_config, validate_config, verify_and_read_ssh_key
from services.ssh_service import run_ssh_command_capture

config_bp = Blueprint('config', __name__)

@config_bp.route("/api/test-connection", methods=["POST"])
def test_connection_endpoint():
    """Validates SSH connection to the Toolforge bastion using request-body config."""
    data = request.json or {}
    config = build_config(data)

    missing = validate_config(config)
    if missing:
        return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

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
