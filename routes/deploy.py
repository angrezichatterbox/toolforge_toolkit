from flask import Blueprint, request, jsonify
from services.config_service import load_config
from services.deploy_service import deploy_from_url
from dotenv import load_dotenv
import os

load_dotenv()

deploy_bp = Blueprint('deploy', __name__)

@deploy_bp.route("/api/deploy", methods=["POST"])
def deploy_endpoint():
    """Endpoint that downloads source code from request URL and deploys to Toolforge."""
    data = request.json or {}
    url = data.get("url")
    username = data.get("username")
    tool_name = data.get("tool_name")
    if not url or not username or not tool_name:
        return jsonify({"success": False, "message": "Missing 'url' parameter in request body"}), 400
        
    load_dotenv()       
    ssh_key = os.getenv("SSH_KEY")
    # Execute pipeline
    result = deploy_from_url(
        url=url,
        username=username,
        tool_name=tool_name,
        ssh_key=ssh_key,
        entry_file=data.get("entry_file"),
        app_var_name=data.get("app_var_name"),
        python_version=data.get("python_version"),
        app_type=data.get("app_type")
    )
    return jsonify(result)
