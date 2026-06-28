from flask import Blueprint, request, jsonify
from services.config_service import load_config, build_config, validate_config
from services.deploy_service import deploy_from_url

deploy_bp = Blueprint('deploy', __name__)

@deploy_bp.route("/api/deploy", methods=["POST"])
def deploy_endpoint():
    """Endpoint that downloads source code from request URL and deploys to Toolforge."""
    data = request.json or {}
    url = data.get("url")
    if not url:
        return jsonify({"success": False, "message": "Missing 'url' parameter in request body"}), 400

    # Start from saved config (has username, bastion_host, ssh_key), then
    # let request body override tool_name and any other per-deploy values.
    config = load_config()
    runtime = build_config(data)
    if runtime.get("tool_name"):
        config["tool_name"] = runtime["tool_name"]

    missing = validate_config(config)
    if missing:
        return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

    # Extract env vars here to pass them separately
    env_vars = data.get("env_vars", {})

    # Execute pipeline
    result = deploy_from_url(config, data, env_vars)
    return jsonify(result)
