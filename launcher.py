import os
import sys
import subprocess
import urllib.request

# Define working directory in Downloads
workspace = os.path.join(os.path.expanduser("~"), "Downloads", "character.py")

# Create folder if it doesn't exist
if not os.path.exists(workspace):
    os.makedirs(workspace)

# Define file URLs
pychai_url = "https://raw.githubusercontent.com/cdexstra1/character.py/main/pychai.py"
requirements_url = "https://raw.githubusercontent.com/cdexstra1/character.py/main/requirements.txt"  # Corrected typo here

# Define local file paths
pychai_path = os.path.join(workspace, "pychai.py")
requirements_path = os.path.join(workspace, "requirements.txt")

# Download function
def download_file(url, path):
    try:
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, path)
        print(f"Saved to {path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

# Download pychai.py and requirements.txt
download_file(pychai_url, pychai_path)
download_file(requirements_url, requirements_path)

# Install dependencies (if requirements.txt exists)
if os.path.exists(requirements_path):
    print("Installing dependencies from requirements.txt...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements_path], check=True)

# Ensure 'memory' folder is created in Downloads (or any safe folder under Downloads)
folder = os.path.join(workspace, "memory")
if not os.path.exists(folder):
    os.makedirs(folder)

# Run pychai.py
if os.path.exists(pychai_path):
    print(f"Running {pychai_path}...")
    subprocess.run([sys.executable, pychai_path], check=True)
else:
    print("Error: pychai.py not found. Check your GitHub URL.")
