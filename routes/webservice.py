from flask import Blueprint, request, jsonify
from services.config_service import load_config
from services.ssh_service import run_ssh_command_capture

webservice_bp = Blueprint('webservice', __name__)

@webservice_bp.route("/api/webservice/status", methods=["GET"])
def webservice_status():
    """Gets the Toolforge web service status."""
    config = load_config()
    stdout, stderr, code = run_ssh_command_capture(config, "toolforge webservice status", as_tool=True)
    return jsonify({"success": (code == 0), "status": stdout or stderr or "Unknown Status"})

@webservice_bp.route("/api/webservice/control", methods=["POST"])
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
