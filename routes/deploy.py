from flask import Blueprint, request, jsonify
from services.config_service import load_config
from services.deploy_service import deploy_from_url

deploy_bp = Blueprint('deploy', __name__)

@deploy_bp.route("/api/deploy", methods=["POST"])
def deploy_endpoint():
    """Endpoint that downloads source code from request URL and deploys to Toolforge."""
    data = request.json or {}
    url = data.get("url")
    if not url:
        return jsonify({"success": False, "message": "Missing 'url' parameter in request body"}), 400
        
    config = load_config()
    
    # Support overriding values from request body
    for field in ["username", "tool_name", "ssh_key", "bastion_host"]:
        if field in data and data[field]:
            config[field] = data[field].strip()
            
    if not config.get("username") or not config.get("tool_name"):
        return jsonify({"success": False, "message": "Wikimedia username and tool name must be configured."}), 400
        
    # Execute pipeline
    result = deploy_from_url(config, data)
    return jsonify(result)
