import json
import os
import hashlib
import requests
import time # For potential rate limiting

MANIFEST_FILE = 'trinkets.json'
TRINKET_CONTENT_REPO = os.environ.get('TRINKET_CONTENT_REPO')
TRINKET_CONTENT_REF = os.environ.get('TRINKET_CONTENT_REF')

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
        for trinket in manifest_data:
            # Only update the trinket that points to the TRINKET_CONTENT_REPO
            # You might need more sophisticated logic here if you have multiple trinkets
            # pointing to different repos, or if you want to update all of them.
            if TRINKET_CONTENT_REPO in trinket.get('appUrl', ''):
                print(f"Processing trinket: {trinket.get('name')} (ID: {trinket.get('id')})")
                
                # Construct the GitHub zipball URL for the content repository
                # Use the archive/refs/heads or archive/refs/tags format for direct zip download
                zipball_url = f"https://api.github.com/repos/{TRINKET_CONTENT_REPO}/zipball/{TRINKET_CONTENT_REF}"
                # If you want to use a specific tag, you'd change TRINKET_CONTENT_REF to the tag name
                # and the URL to: f"https://github.com/{TRINKET_CONTENT_REPO}/archive/refs/tags/{TRINKET_CONTENT_REF}.zip"

                new_hash = calculate_sha256_from_url(zipball_url)
                
                if new_hash and new_hash != trinket.get('hash'):
                    print(f"Hash updated for {trinket.get('name')}: {trinket.get('hash')} -> {new_hash}")
                    trinket['hash'] = new_hash
                    trinket['ref'] = TRINKET_CONTENT_REF # Update ref to match what was hashed
                    updated = True
                elif new_hash:
                    print(f"Hash for {trinket.get('name')} is already up-to-date: {new_hash}")
                else:
                    print(f"Failed to calculate new hash for {trinket.get('name')}. Skipping update.")
            
            # Add a small delay to avoid hitting GitHub API rate limits if processing many trinkets
            time.sleep(1)

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