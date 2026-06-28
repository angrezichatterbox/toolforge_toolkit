import json
from flask import Blueprint, request, jsonify
from services.config_service import load_config, build_config, validate_config
from services.ssh_service import run_ssh_command_capture

webservice_bp = Blueprint('webservice', __name__)

# Maps Toolforge deployment states → our frontend status values
_STATE_MAP = {
    "successful": "running",
    "running":    "deploying",
    "pending":    "deploying",
    "failed":     "error",
    "timed_out":  "error",
    "cancelling": "stopped",
    "cancelled":  "stopped",
}

def _get_config(data):
    """Merge saved config with any overrides from request body."""
    config = load_config()
    runtime = build_config(data)
    if runtime.get("tool_name"):
        config["tool_name"] = runtime["tool_name"]
    if runtime.get("username"):
        config["username"] = runtime["username"]
    return config


@webservice_bp.route("/api/webservice/status", methods=["POST"])
def webservice_status():
    """Gets the live webservice status via the Toolforge components API."""
    data = request.json or {}
    config = _get_config(data)

    missing = validate_config(config)
    if missing:
        return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

    tool_name = config["tool_name"]

    # Call the Toolforge components API as the tool user (has x509 certs in ~/.toolskube/)
    curl_cmd = (
        f"curl -sf "
        f"--cert ~/.toolskube/client.crt "
        f"--key ~/.toolskube/client.key "
        f"https://api.svc.toolforge.org/components/v1/tool/{tool_name}/deployment/latest"
    )
    stdout, stderr, code = run_ssh_command_capture(config, curl_cmd, as_tool=True)

    if code != 0 or not stdout.strip():
        # Fall back to plain `toolforge webservice status` text output
        stdout2, stderr2, code2 = run_ssh_command_capture(config, "toolforge webservice status", as_tool=True)
        return jsonify({"success": (code2 == 0), "status": stdout2 or stderr2 or "unknown"})

    try:
        payload = json.loads(stdout)
        deploy_state = payload.get("data", {}).get("status", "unknown")
        mapped = _STATE_MAP.get(deploy_state, "unknown")
        long_status = payload.get("data", {}).get("long_status", "")
        return jsonify({
            "success": True,
            "status": mapped,
            "raw_state": deploy_state,
            "detail": long_status,
        })
    except (json.JSONDecodeError, AttributeError):
        return jsonify({"success": True, "status": stdout.strip()})


@webservice_bp.route("/api/webservice/control", methods=["POST"])
def webservice_control():
    """Controls the webservice lifecycle (start, stop, restart)."""
    data = request.json or {}
    action = data.get("action")
    ws_type = data.get("type", "python3.11")

    if action not in ["start", "stop", "restart"]:
        return jsonify({"success": False, "message": "Invalid action. Choose 'start', 'stop', or 'restart'."}), 400

    config = _get_config(data)
    missing = validate_config(config)
    if missing:
        return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

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
