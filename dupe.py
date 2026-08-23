import os
import json
import hashlib

IMAGE_DIR = "pinterest_images"
JSON_FILE = "metadata.json"

def calculate_sha256(filepath):
    """Calculates SHA-256 hash of a file to detect exact visual/binary duplicates"""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def remove_duplicates():
    if not os.path.exists(IMAGE_DIR):
        print(f"dir not found '{IMAGE_DIR}'")
        return

    seen_hashes = {}
    removed_files = set()
    kept_count = 0
    deleted_count = 0

    image_files = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
    print(f" {len(image_files)}...\n")

    for filename in image_files:
        filepath = os.path.join(IMAGE_DIR, filename)
        
        try:
            file_hash = calculate_sha256(filepath)

            if file_hash in seen_hashes:
                original_file = seen_hashes[file_hash]
                print(f"deleting {filename} (dupe of {original_file})")
                os.remove(filepath)
                removed_files.add(filename)
                deleted_count += 1
            else:
                seen_hashes[file_hash] = filename
                kept_count += 1

        except Exception as e:
            print(f"couldnt process {filename}: {e}")

    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        updated_metadata = [item for item in metadata if item.get("filename") not in removed_files]

        for idx, item in enumerate(updated_metadata, start=1):
            item["id"] = idx

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_metadata, f, indent=2)

        print(f"\n[METADATA] Updated '{JSON_FILE}'. Removed {len(removed_files)} entries.")

    print(f"\nkept {kept_count} unique images, deleted {deleted_count} duplicates.")

if __name__ == "__main__":
    remove_duplicates()