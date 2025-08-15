import json
import os
import hashlib
import requests
import time # For potential rate limiting
import zipfile
import shutil
import tempfile

MANIFEST_FILE = 'trinkets.json'
TRINKET_CONTENT_REPO = os.environ.get('TRINKET_CONTENT_REPO')
TRINKET_CONTENT_REF = os.environ.get('TRINKET_CONTENT_REF')

EXCLUDE_PATTERNS = ['.git', '.github', '.vscode', '__pycache__', '.DS_Store']

if not all([TRINKET_CONTENT_REPO, TRINKET_CONTENT_REF]):
    print("Error: Missing TRINKET_CONTENT_REPO or TRINKET_CONTENT_REF environment variables.")
    exit(1)

def calculate_sha256_from_url(url):
    """Downloads content from a URL and calculates its SHA256 hash."""
    print(f"Downloading {url} to calculate hash...")
    try:
        # GitHub API requires a User-Agent header
        headers = {'User-Agent': 'GitHubActions-TrinketManifestUpdater'}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status() # Raise an exception for HTTP errors

        hasher = hashlib.sha256()
        for chunk in response.iter_content(chunk_size=8192):
            hasher.update(chunk)
        print("Hash calculation complete.")
        return hasher.hexdigest()
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return None

try:
    with open(MANIFEST_FILE, 'r+') as f:
        manifest_data = json.load(f)

        updated = False
        existing_trinket_ids = {t['id'] for t in manifest_data}

        # 1. Download TrinketCollection zipball and calculate its hash
        zipball_url = f"https://api.github.com/repos/{TRINKET_CONTENT_REPO}/zipball/{TRINKET_CONTENT_REF}"
        new_repo_hash = calculate_sha256_from_url(zipball_url)

        if not new_repo_hash:
            print("Failed to get new repository hash. Exiting.")
            exit(1)

        # 2. Download and Extract TrinketCollection to identify new folders
        print(f"Downloading TrinketCollection zipball from {zipball_url} for folder discovery...")
        try:
            headers = {'User-Agent': 'GitHubActions-TrinketManifestUpdater'}
            response = requests.get(zipball_url, headers=headers, stream=True)
            response.raise_for_status()

            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "trinket_collection.zip")
                with open(zip_path, 'wb') as zf:
                    for chunk in response.iter_content(chunk_size=8192):
                        zf.write(chunk)

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    extract_path = os.path.join(tmpdir, "extracted_repo")
                    zip_ref.extractall(extract_path)

                repo_root_dir = None
                for item in os.listdir(extract_path):
                    if os.path.isdir(os.path.join(extract_path, item)):
                        repo_root_dir = os.path.join(extract_path, item)
                        break
                
                if not repo_root_dir:
                    print("Error: Could not find repository root directory in extracted zip.")
                    exit(1)

                # 3. Identify Trinket Folders and Add New Entries
                for trinket_folder_name in os.listdir(repo_root_dir):
                    if trinket_folder_name in EXCLUDE_PATTERNS:
                        print(f"Skipping excluded folder: {trinket_folder_name}")
                        continue
                    trinket_folder_path = os.path.join(repo_root_dir, trinket_folder_name)
                    if os.path.isdir(trinket_folder_path):
                        trinket_id = trinket_folder_name # Assuming folder name is the ID

                        if trinket_id not in existing_trinket_ids:
                            print(f"Found new trinket: {trinket_id}. Adding to manifest.")
                            new_trinket_entry = {
                                "id": trinket_id,
                                "name": trinket_id.replace('-', ' ').title(), # Simple name generation
                                "appUrl": f"https://Nishimba.github.io/TrinketCollection/{trinket_id}/index.html",
                                "iconUrl": f"https://Nishimba.github.io/TrinketCollection/{trinket_id}/icon.png",
                                "entryFile": f"https://Nishimba.github.io/TrinketCollection/{trinket_id}/index.html",
                                "hash": new_repo_hash, # Use the hash of the entire repo
                                "ref": TRINKET_CONTENT_REF
                            }
                            manifest_data.append(new_trinket_entry)
                            updated = True
                            existing_trinket_ids.add(trinket_id) # Add to set to avoid re-adding

        except requests.exceptions.RequestException as e:
            print(f"Error downloading or extracting TrinketCollection: {e}")
            exit(1)
        except zipfile.BadZipFile:
            print("Error: Downloaded file is not a valid zip file.")
            exit(1)
        except Exception as e:
            print(f"An unexpected error occurred during zipball processing: {e}")
            exit(1)

        # 4. Update existing trinket hashes (all use the new_repo_hash)
        for trinket in manifest_data:
            if TRINKET_CONTENT_REPO in trinket.get('appUrl', ''):
                if trinket.get('hash') != new_repo_hash:
                    print(f"Updating hash for {trinket.get('name')}: {trinket.get('hash')} -> {new_repo_hash}")
                    trinket['hash'] = new_repo_hash
                    trinket['ref'] = TRINKET_CONTENT_REF
                    updated = True
                else:
                    print(f"Hash for {trinket.get('name')} is already up-to-date: {new_repo_hash}")
            
            time.sleep(0.1)

        if updated:
            f.seek(0)
            json.dump(manifest_data, f, indent=2)
            f.truncate()
            print(f"{MANIFEST_FILE} updated successfully.")
        else:
            print(f"No changes needed for {MANIFEST_FILE}.")

except FileNotFoundError:
    print(f"Error: {MANIFEST_FILE} not found.")
    exit(1)
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from {MANIFEST_FILE}. Check file format.")
    exit(1)