#!/usr/bin/env python3
"""
GitHub Action PR Creator
Automates the process of raising a pull request to a GitHub repository 
containing a continuous deployment workflow template depending on the app type (flask/node).
"""

import os
import re
import json
import uuid
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error

def parse_github_url(url):
    """
    Parses a GitHub repository URL to extract the owner and repository name.
    Supports both HTTPS and SSH format.
    """
    pattern = r'(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+)(?:\.git)?'
    match = re.search(pattern, url)
    if match:
        owner = match.group(1)
        repo = match.group(2)
        return owner, repo
    raise Exception(f"Could not parse owner and repo name from GitHub URL: {url}")

def create_pull_request(owner, repo, title, head, base, body, token):
    """
    Uses the GitHub REST API to create a Pull Request.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = {
        "title": title,
        "head": head,
        "base": base,
        "body": body
    }
    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Toolforge-Manager-PR-Creator",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        raise Exception(f"GitHub API Error ({e.code}): {err_msg}")

def create_github_action_pr(repo_url, app_type, github_token=None):
    """
    Selects the continuous deployment workflow file from the current directory,
    clones the target repository, commits the workflow, pushes it, and opens a GitHub PR.
    
    Parameters:
        repo_url (str): The HTTPS or SSH URL of the target GitHub repository.
        app_type (str): The application framework type ('flask' or 'node').
        github_token (str, optional): GitHub Personal Access Token. If omitted,
                                     looks for the GITHUB_TOKEN environment variable.
                                     
    Returns:
        dict: Success status, PR URL, and branch names.
    """
    if not github_token:
        github_token = os.environ.get("GITHUB_TOKEN")
        if not github_token:
            raise Exception("GitHub personal access token is required. Pass it to the function or set the GITHUB_TOKEN env var.")

    # 1. Parse repository URL
    owner, repo = parse_github_url(repo_url)
    print(f"Target repository: {owner}/{repo}")

    # 2. Select workflow template file from current directory
    workflow_files = {
        "flask": "flask_cd.yml",
        "node": "node_cd.yml"
    }
    
    app_type_clean = app_type.lower().strip()
    source_file = workflow_files.get(app_type_clean)
    
    if not source_file:
        raise Exception(f"Unsupported app type: '{app_type}'. Supported types: 'flask', 'node'")
        
    if not os.path.exists(source_file):
        raise Exception(f"Workflow template file '{source_file}' not found in current directory.")

    with open(source_file, "r", encoding="utf-8") as f:
        workflow_content = f.read()

    # 3. Perform Git and API operations in a temporary directory
    temp_dir = tempfile.mkdtemp()
    try:
        # Use authenticated URL for git operations
        auth_url = f"https://x-access-token:{github_token}@github.com/{owner}/{repo}.git"
        
        print(f"Cloning repository into temporary directory...")
        clone_res = subprocess.run(["git", "clone", auth_url, temp_dir], capture_output=True, text=True)
        if clone_res.returncode != 0:
            clean_err = clone_res.stderr.replace(github_token, "********")
            raise Exception(f"Git clone failed: {clean_err}")

        # Get default branch name (usually main or master)
        default_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
            cwd=temp_dir, 
            capture_output=True, 
            text=True, 
            check=True
        ).stdout.strip()
        print(f"Detected default branch: {default_branch}")

        # Create a new branch for the PR
        branch_suffix = str(uuid.uuid4())[:8]
        new_branch = f"add-cd-workflow-{app_type_clean}-{branch_suffix}"
        print(f"Creating new branch: {new_branch}")
        subprocess.run(["git", "checkout", "-b", new_branch], cwd=temp_dir, check=True)

        # Ensure directory structure exists and write workflow file
        workflows_dir = os.path.join(temp_dir, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        dest_file_path = os.path.join(workflows_dir, "deploy.yml")
        
        with open(dest_file_path, "w", encoding="utf-8") as f:
            f.write(workflow_content)
        print(f"Copied {source_file} template contents to {dest_file_path}")

        # Configure local git repository context for commit
        subprocess.run(["git", "config", "user.name", "Toolforge Manager PR Creator"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "user.email", "toolforge-manager@local"], cwd=temp_dir, check=True)
        
        # Add, commit and push changes
        subprocess.run(["git", "add", ".github/workflows/deploy.yml"], cwd=temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", f"Add Continuous Deployment action workflow for {app_type_clean}"], cwd=temp_dir, check=True)
        
        print(f"Pushing branch {new_branch} to origin...")
        push_res = subprocess.run(["git", "push", "origin", new_branch], cwd=temp_dir, capture_output=True, text=True)
        if push_res.returncode != 0:
            clean_err = push_res.stderr.replace(github_token, "********")
            raise Exception(f"Git push failed: {clean_err}")

        # Create the PR via GitHub REST API
        print("Creating Pull Request on GitHub...")
        pr_title = f"Add CI/CD Workflow for {app_type.capitalize()}"
        pr_body = (
            f"This PR adds a default GitHub Action workflow for Continuous Deployment "
            f"configured specifically for **{app_type.capitalize()}** applications.\n\n"
            f"Workflow file added: `.github/workflows/deploy.yml`"
        )
        
        pr_response = create_pull_request(
            owner=owner,
            repo=repo,
            title=pr_title,
            head=new_branch,
            base=default_branch,
            body=pr_body,
            token=github_token
        )
        
        pr_url = pr_response.get("html_url")
        print(f"Successfully raised Pull Request! URL: {pr_url}")
        
        return {
            "success": True,
            "pr_url": pr_url,
            "branch": new_branch,
            "default_branch": default_branch
        }

    except Exception as e:
        print(f"Error executing PR pipeline: {e}")
        return {"success": False, "error": str(e)}
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

