import os
import json

JSON_FILE = "metadata.json"
IMAGE_DIR = "pinterest_images"

def sync_metadata():
    if not os.path.exists(JSON_FILE):
        print(f"[ERROR] '{JSON_FILE}' does not exist.")
        return

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    original_count = len(metadata)
    updated_metadata = []

    for item in metadata:
        filename = item.get("filename")
        filepath = os.path.join(IMAGE_DIR, filename)

        if os.path.exists(filepath):
            updated_metadata.append(item)

    for idx, item in enumerate(updated_metadata, start=1):
        item["id"] = idx

    removed_count = original_count - len(updated_metadata)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_metadata, f, indent=2)

    print(f"Sync complete.")
    print(f"Original entries: {original_count}")
    print(f"Removed entries:  {removed_count}")
    print(f"Remaining entries: {len(updated_metadata)}")

if __name__ == "__main__":
    sync_metadata()