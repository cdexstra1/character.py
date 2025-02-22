import os
import sys
import subprocess
import urllib.request

# Admin Elevation Check (for non-admin runs)
def run_as_admin():
    if not os.getenv('SUDO_UID'):  # Check if it's running as root
        subprocess.run(['runas', '/user:Administrator', sys.executable] + sys.argv)  # Run script as Administrator

# Call the function to elevate if needed
run_as_admin()

# Define working directory in Downloads
workspace = os.path.join(os.path.expanduser("~"), "Downloads", "character.py")
os.makedirs(workspace, exist_ok=True)

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

# Install dependencies
if os.path.exists(requirements_path):
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements_path], check=True)

# Ensure 'memory' folder is created in Downloads (or any safe folder under Downloads)
folder = os.path.join(os.path.expanduser("~"), "Downloads", "character.py", "memory")  # Adjusted path
os.makedirs(folder, exist_ok=True)

# Run pychai.py
if os.path.exists(pychai_path):
    subprocess.run([sys.executable, pychai_path], check=True)
else:
    print("Error: pychai.py not found. Check your GitHub URL.")
