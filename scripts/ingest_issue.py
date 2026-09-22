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
        
    packages_dir = Path("web/packages")
    packages_dir.mkdir(parents=True, exist_ok=True)
    temp_path = packages_dir / "temp_download.zip"

    # 1. Check for embedded Base64 payload first (fastest & most reliable)
    b64_match = re.search(r'<!-- MAGICEXT_BASE64_START -->\s*([A-Za-z0-9+/=\s]+)\s*<!-- MAGICEXT_BASE64_END -->', body)
    if b64_match:
        import base64
        print("Found embedded Base64 package data. Decoding...")
        raw_b64 = re.sub(r'\s+', '', b64_match.group(1))
        file_bytes = base64.b64decode(raw_b64)
        with open(temp_path, 'wb') as f:
            f.write(file_bytes)
        print("✓ Successfully decoded package from issue body.")
    else:
        # 2. Check for tmpfiles.org URL
        tmpfiles_match = re.search(r'(https://tmpfiles\.org/(?:dl/)?[a-zA-Z0-9]+/[a-zA-Z0-9_.-]+)', body)
        # 3. Check for GitHub attachments
        gh_match = re.search(r'(https://github\.com/user-attachments/(?:assets|files)/[^\s\)\"\'>]+)', body)

        if tmpfiles_match:
            view_url = tmpfiles_match.group(1)
            print(f"Fetching from tmpfiles: {view_url}")
            req = urllib.request.Request(view_url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                page_content = urllib.request.urlopen(req).read()
                # Check if it was direct binary or HTML landing page
                if page_content.startswith(b'PK\x03\x04'):
                    with open(temp_path, 'wb') as f:
                        f.write(page_content)
                else:
                    html_text = page_content.decode('utf-8', errors='ignore')
                    dl_links = re.findall(r'href=[\"\'](https://tmpfiles\.org/dl/[^\"\']+)[\"\']', html_text)
                    if not dl_links:
                        print("Error: Could not extract download link from tmpfiles page.")
                        exit(1)
                    real_dl_url = dl_links[0]
                    print(f"Downloading from tmpfiles link: {real_dl_url}")
                    dl_req = urllib.request.Request(real_dl_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(dl_req) as resp, open(temp_path, 'wb') as f:
                        f.write(resp.read())
            except Exception as e:
                print(f"Error downloading from tmpfiles: {e}")
                exit(1)
        elif gh_match:
            url = gh_match.group(1)
            print(f"Downloading GitHub attachment: {url}")
            try:
                try:
                    import requests
                    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                    resp.raise_for_status()
                    with open(temp_path, 'wb') as out_file:
                        out_file.write(resp.content)
                except ImportError:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=30) as response, open(temp_path, 'wb') as out_file:
                        out_file.write(response.read())
            except Exception as e:
                print(f"Error downloading attachment: {e}")
                exit(1)
        else:
            print("Error: Could not find any package data or attachment URL in the issue body.")
            exit(1)

    print("Package downloaded / extracted successfully.")
    
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
