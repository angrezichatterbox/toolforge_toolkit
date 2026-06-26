import os
import shutil
import tempfile
import zipfile
import tarfile
import urllib.request
import subprocess

def download_source_files(url, target_dir):
    """
    Downloads or clones the source files from the given URL into target_dir.
    Supports Git repositories and Zip/Tarball archives.
    """
    url_lower = url.lower()
    
    # Check if it looks like a Git URL
    is_git = False
    if url_lower.endswith(".git") or "git@" in url_lower or "gerrit.wikimedia.org" in url_lower:
        is_git = True
    elif "github.com" in url_lower or "gitlab.com" in url_lower:
        if "/archive/" not in url_lower and "/zip/" not in url_lower and "/releases/" not in url_lower:
            is_git = True

    if is_git:
        print(f"Cloning Git repository from: {url}")
        result = subprocess.run(["git", "clone", url, target_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr or result.stdout}")
        return "git"

    # Treat it as a direct archive download
    print(f"Downloading archive from: {url}")
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_path = temp_file.name
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(temp_file_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        # Detect archive format and extract
        if zipfile.is_zipfile(temp_file_path):
            print("Extracting ZIP archive...")
            with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        elif tarfile.is_tarfile(temp_file_path):
            print("Extracting TAR archive...")
            with tarfile.open(temp_file_path, 'r:*') as tar_ref:
                tar_ref.extractall(target_dir)
        else:
            raise Exception("Unsupported archive format. Provide a ZIP, TAR, or Git repository URL.")
            
        # Flatten structure if the archive extracted all contents into a single nested directory
        subdirs = os.listdir(target_dir)
        if len(subdirs) == 1 and os.path.isdir(os.path.join(target_dir, subdirs[0])):
            nested_dir = os.path.join(target_dir, subdirs[0])
            print(f"Promoting nested directory contents from {subdirs[0]} to root...")
            for item in os.listdir(nested_dir):
                shutil.move(os.path.join(nested_dir, item), os.path.join(target_dir, item))
            os.rmdir(nested_dir)
            
        return "archive"
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
