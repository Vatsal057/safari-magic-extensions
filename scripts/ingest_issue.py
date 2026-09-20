import os
import re
import urllib.request
import zipfile
import json
from pathlib import Path

def main():
    body = os.getenv("ISSUE_BODY", "")
    if not body:
        print("Error: ISSUE_BODY environment variable is empty.")
        exit(1)
        
    # Check for tmpfiles.org URL first
    tmpfiles_match = re.search(r'(https://tmpfiles\.org/[a-zA-Z0-9]+/[a-zA-Z0-9_.-]+)', body)
    if tmpfiles_match:
        view_url = tmpfiles_match.group(1)
        # Convert view URL to direct download URL
        url = view_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/', 1)
        print(f"Found tmpfiles URL: {url}")
    else:
        # Fallback to GitHub attachments
        match = re.search(r'(https://github\.com/user-attachments/assets/[a-zA-Z0-9-]+)', body)
        if not match:
            print("Error: Could not find a .magicext attachment URL (tmpfiles or github) in the issue body.")
            exit(1)
        url = match.group(1)
        print(f"Found GitHub attachment URL: {url}")
    
    packages_dir = Path("web/packages")
    packages_dir.mkdir(parents=True, exist_ok=True)
    
    # Download to a temporary file first
    temp_path = packages_dir / "temp_download.zip"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response, open(temp_path, 'wb') as out_file:
            out_file.write(response.read())
    except Exception as e:
        print(f"Error downloading attachment: {e}")
        exit(1)
        
    print("Download successful.")
    
    # Extract the name from the magic.json to rename the file properly
    extension_name = "Extension"
    try:
        with zipfile.ZipFile(temp_path, 'r') as zf:
            with zf.open("magic.json") as f:
                magic_data = json.load(f)
                extension_name = magic_data.get("name", "Extension")
    except Exception as e:
        print(f"Error reading magic.json from downloaded package: {e}")
        temp_path.unlink(missing_ok=True)
        exit(1)
        
    # Slugify the name to get a clean filename
    slug = re.sub(r'[^a-z0-9]+', '-', extension_name.lower()).strip('-') or 'extension'
    final_path = packages_dir / f"{slug}.magicext"
    
    temp_path.rename(final_path)
    print(f"Saved package as {final_path}")

if __name__ == "__main__":
    main()
