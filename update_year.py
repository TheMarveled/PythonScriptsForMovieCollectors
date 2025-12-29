"""
Movie Year Renamer (TMDb) with junk cleanup, undo, dry-run, and dynamic collection-based folder sorting.

Features:
- Recursive folder scanning
- Supports multiple video formats
- Adds movie release year from TMDb
- Optional junk cleanup (remove 1080p, BluRay, x264, HDR, etc.)
- Undo last batch of renames using a log file
- Dry-run mode
- Automatically sorts movies into folders based on TMDb collection (franchise)
- Prompts user for TMDb API key if not set

TMDb API signup: https://www.themoviedb.org/signup
"""

import os
import re
import time
import sys
import subprocess

# -----------------------------
# AUTO-INSTALL DEPENDENCIES
# -----------------------------
try:
    import requests
except ImportError:
    print("Installing missing dependency: requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# -----------------------------
# USER CONFIGURATION
# -----------------------------
ROOT_FOLDER = r"/Movies"  # Change to your movie folder
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".webm"}
TMDB_API_KEY = "PASTE_YOUR_TMDB_API_KEY_HERE"  # Or leave placeholder to enter via console
LOG_FILE = "rename_log.txt"
API_DELAY = 0.25  # Delay between TMDb requests

YEAR_PATTERN = re.compile(r"\(\d{4}\)")
JUNK_PATTERN = re.compile(
    r"(1080p|720p|480p|BluRay|BRRip|DVDRip|HDR|WEBRip|x264|x265|HEVC|AAC|DTS|H\.264|H\.265)",
    re.IGNORECASE
)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def has_year(filename: str) -> bool:
    return bool(YEAR_PATTERN.search(filename))

def clean_title(filename: str, remove_junk=False) -> str:
    name = os.path.splitext(filename)[0].strip()
    if remove_junk:
        name = JUNK_PATTERN.sub("", name).strip()
        name = re.sub(r"[\._]+", " ", name)
        name = re.sub(r"\s{2,}", " ", name)
    return name

def get_movie_data(title: str) -> dict | None:
    """Fetch full TMDb movie metadata, including release date and collection info."""
    search_url = "https://api.themoviedb.org/3/search/movie"
    params = {"api_key": TMDB_API_KEY, "query": title}

    try:
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        # Take first result with a valid release date
        movie = next((m for m in results if m.get("release_date")), None)
        if not movie:
            return None

        # Fetch full movie details
        movie_id = movie["id"]
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        details_params = {"api_key": TMDB_API_KEY}
        details_resp = requests.get(details_url, params=details_params, timeout=10)
        details_resp.raise_for_status()
        return details_resp.json()

    except Exception as e:
        print(f"TMDb error for '{title}': {e}")
        return None

# -----------------------------
# MENU / UTILITY FUNCTIONS
# -----------------------------
def prompt_yes_no(message: str) -> bool:
    while True:
        choice = input(f"{message} [y/n]: ").strip().lower()
        if choice in {"y", "yes"}:
            return True
        elif choice in {"n", "no"}:
            return False
        else:
            print("Please enter y or n.")

def get_api_key_from_user() -> str:
    print("TMDb API key is not set.")
    print("Sign up for a free API key at: https://www.themoviedb.org/signup")
    key = input("Paste your TMDb API key here: ").strip()
    return key

def undo_last_batch():
    """Revert all renames recorded in the log file."""
    if not os.path.exists(LOG_FILE):
        print("No log file found. Nothing to undo.")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if not lines:
        print("Log file is empty. Nothing to undo.")
        return

    for line in reversed(lines):
        if " -> " not in line:
            continue
        old_path, new_path = line.split(" -> ", 1)
        if os.path.exists(new_path):
            try:
                os.makedirs(os.path.dirname(old_path), exist_ok=True)
                os.rename(new_path, old_path)
                print(f"Reverted: {new_path} → {old_path}")
            except Exception as e:
                print(f"Failed to revert {new_path}: {e}")
        else:
            print(f"File not found, cannot revert: {new_path}")

    os.remove(LOG_FILE)
    print("Undo complete. Log file cleared.")

# -----------------------------
# MAIN RENAME FUNCTION
# -----------------------------
def rename_movies():
    global TMDB_API_KEY

    if not TMDB_API_KEY or TMDB_API_KEY == "PASTE_YOUR_TMDB_API_KEY_HERE":
        TMDB_API_KEY = get_api_key_from_user()
        if not TMDB_API_KEY:
            print("No API key provided. Exiting.")
            return

    clean_junk = prompt_yes_no("Do you want to clean junk (1080p, BluRay, x264, etc.) from filenames?")
    dry_run = prompt_yes_no("Do you want to run in dry-run mode (no files will be renamed)?")
    sort_collections = prompt_yes_no("Do you want to sort movies into folders based on TMDb collections?")

    print("\nStarting scan...\n")

    with open(LOG_FILE, "a", encoding="utf-8") as log:
        for root, _, files in os.walk(ROOT_FOLDER):
            for file in files:
                name, ext = os.path.splitext(file)
                ext = ext.lower()

                if ext not in VIDEO_EXTENSIONS:
                    continue
                if has_year(file):
                    continue

                title = clean_title(file, remove_junk=clean_junk)
                movie_data = get_movie_data(title)

                if not movie_data or not movie_data.get("release_date"):
                    print(f"Year not found: {title}")
                    continue

                year = movie_data["release_date"][:4]

                # Determine target folder
                target_folder = root
                if sort_collections and movie_data.get("belongs_to_collection"):
                    collection_name = movie_data["belongs_to_collection"]["name"]
                    target_folder = os.path.join(ROOT_FOLDER, collection_name)
                    os.makedirs(target_folder, exist_ok=True)

                new_name = f"{title} ({year}){ext}"
                old_path = os.path.join(root, file)
                new_path = os.path.join(target_folder, new_name)

                if os.path.exists(new_path):
                    print(f"Skipped (already exists): {new_name}")
                    continue

                if dry_run:
                    print(f"[DRY-RUN] Would rename: {file} → {new_name}")
                else:
                    os.rename(old_path, new_path)
                    log.write(f"{old_path} -> {new_path}\n")
                    print(f"Renamed: {file} → {new_name}")

                time.sleep(API_DELAY)


# -----------------------------
# INTERACTIVE MENU
# -----------------------------
def main_menu():
    while True:
        print("\n=== Movie Year Renamer ===")
        print("1. Rename movies")
        print("2. Undo last batch of renames")
        print("3. Exit")

        choice = input("Select an option [1-3]: ").strip()
        if choice == "1":
            rename_movies()
        elif choice == "2":
            undo_last_batch()
        elif choice == "3":
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    main_menu()
