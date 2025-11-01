#!/bin/env python3

# I've now realized mpremote does everything this script does and more, so it should
# probably be deleted.

import argparse
import binascii
import hashlib
import os
import pathlib
import subprocess
from typing import Iterable, Optional


def get_git_changed_files() -> set[str]:
    """Get list of files changed according to git status."""
    try:
        # Get git root directory and current directory
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()

        current_dir = os.getcwd()

        # Calculate relative path from git root to current directory
        try:
            rel_path = os.path.relpath(current_dir, git_root)
            if rel_path == ".":
                rel_path = ""
            else:
                rel_path = rel_path.replace("\\", "/") + "/"
        except ValueError:
            # Different drives on Windows
            rel_path = ""

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = set()
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Git status format: "XY filename" where XY is the status code
            status = line[:2]
            filename = line[3:].strip()
            # Remove quotes if present
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]

            # Normalize path separators
            filename = filename.replace("\\", "/")

            # Check if file is in the badge/ directory (accounting for git root vs current dir)
            target_prefix = rel_path + "badge/"
            if filename.startswith(target_prefix):
                # Convert to path relative to current directory
                changed_files.add(filename[len(rel_path):])
            elif filename.startswith("badge/") and rel_path == "":
                # Already in the right format
                changed_files.add(filename)

        return changed_files
    except subprocess.CalledProcessError as e:
        print(f"Error running git status: {e}")
        return set()

def check_path(path: str, filter_files: Optional[set[str]] = None) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    top_path = pathlib.Path(path)
    for file_path in top_path.iterdir():
        posix_path = file_path.as_posix()

        # If filtering is enabled and this path doesn't match, skip it
        if filter_files is not None:
            # Check if this file or any parent directory is in the filter set
            should_include = False
            if posix_path in filter_files:
                should_include = True
            else:
                # Check if any file in filter_files is under this directory
                for filtered_file in filter_files:
                    if filtered_file.startswith(posix_path + "/"):
                        should_include = True
                        break
            if not should_include:
                continue

        if file_path.is_file():
            with open(file_path, "rb") as file:
                hasher = hashlib.sha256(file.read())
                files[posix_path] = hasher.digest()
        else:
            if file_path.name == "__pycache__":
                continue
            files.update(check_path(str(file_path), filter_files))
            files[posix_path] = b""
    return files

def check_dir(path: str, filter_files: Optional[set[str]] = None) -> dict[str, str]:
    files_uncleaned = check_path(path, filter_files)
    files = {fn.replace(path.strip() + "/", "/").replace("\\", "/"): binascii.hexlify(hash).decode() for fn, hash in files_uncleaned.items()}
    return files

def sort_paths_recursively(paths: Iterable[str]) -> list[str]:
    """Return paths sorted depth-first so parents appear before children."""
    return sorted(paths, key=lambda name: (name.count("/"), name))

def format_recursive_path(name: str) -> str:
    """Indent nested entries to make the hierarchy clearer."""
    depth = max(name.count("/") - 1, 0)
    return f"{'  ' * depth}{name}"

def get_badge_files() -> dict[str, str]:
    """Get the files on the badge and their checksums."""
    badge_files_text = subprocess.run(["mpremote", "run", "./scripts/check_filesystem.py"], capture_output=True, text=True).stdout
    badge_files = {}
    for line in badge_files_text.split("\n"):
        if " " in line:
            try:
                name, checksum = line.split(" ")
                badge_files[name] = checksum.strip()[2:-1]
            except ValueError as err:
                print(err)
                print(line)
    return badge_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Badge Updater")
    parser.add_argument("action", type=str, nargs="?", default="ls", help="Action to perform: 'ls' to list files (default), 'push' to push files, 'pull' to pull files.")
    parser.add_argument("--reset", action="store_true", default=False, help="Reset the badge after.")
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    parser.add_argument("--git-only", "-g", action="store_true", default=False, help="Only process files changed according to git status.")
    args = parser.parse_args()
    if args.action not in ("ls", "list", "push", "pull"):
        print(f"Unknown action '{args.action}'. Use 'ls', 'push', or 'pull'.")
        exit(1)

    # Get git changed files if --git-only is specified
    git_changed_files = None
    if args.git_only:
        git_changed_files = get_git_changed_files()
        if not git_changed_files:
            print("No changed files found in badge/ directory according to git status.")
            if args.action == "push":
                print("Nothing to push.")
                exit(0)
        else:
            print(f"Git changed files in badge/: {len(git_changed_files)} files")
            if args.verbose:
                for f in sorted(git_changed_files):
                    print(f"  {f}")

    if args.action == "push":
        print("Checking badge/ directory...")
        local_files = check_dir("badge", git_changed_files)
        print("Checking files on badge...")
        badge_files = get_badge_files()
        for name in sorted(local_files.keys()):
            hash = local_files[name]
            if name not in badge_files and hash == "":
                print(f"Creating directory {name}...")
                # Don't fail if directory already exists
                result = subprocess.run(["mpremote", "mkdir", name], capture_output=True, text=True)
                if result.returncode != 0 and "File exists" not in result.stderr:
                    print(f"Error creating directory {name}: {result.stderr}")
                    raise subprocess.CalledProcessError(result.returncode, result.args)
            elif name not in badge_files or badge_files[name] != hash:
                if name not in badge_files:
                    print(f"Creating {name}...")
                else:
                    print(f"Updating {name}...")
                subprocess.run(["mpremote", "cp", f"badge{name}", f":{name}"], check=True)
            else:
                if args.verbose:
                    print(f"{name} is up to date.")

        # Only delete files if we're not in git-only mode
        # In git-only mode, we only want to update changed files, not delete everything else
        if not args.git_only:
            files_to_delete = set(badge_files.keys()) - set(local_files.keys())
            for name in sorted(files_to_delete, reverse=True):
                if name.startswith("/data"):  # Don't delete the data/ directory.
                    continue
                if "__pycache__" in name:  # Don't delete cache files
                    continue
                if badge_files[name] == "":
                    # Can't use rmdir because __pycache__ will linger
                    print(f"Removing directory {name} from badge...")
                    subprocess.run(["mpremote", "rm", "-r", name], check=True)
                else:
                    print(f"Deleting {name} from badge...")
                    subprocess.run(["mpremote", "rm", name], check=True)

    if args.action == "pull":
        print("Pulling files from badge...")
        badge_files = get_badge_files()
        if not os.path.exists("badge-backup"):
            os.makedirs("badge-backup")
        file_text = subprocess.run(["mpremote", "cp", "-r", ":", "badge-backup/"], check=True)
        # for name in badge_files.keys():
        #     print(f"Pulling {name}...")
        #     with open(f"badge-backup/{name}", "w") as file:
        #         file.write(file_text)
        print("Files pulled successfully.")

    if args.action in ("ls", "list"):
        local_files = check_dir("badge", git_changed_files)
        badge_files = get_badge_files()
        print("Files on badge:")
        print("Status values: * different, + only on local (push will add), - only on badge (push will delete)")
        print(f"Status {'Filename':<40s} SHA256")
        all_files = set(local_files.keys()).union(set(badge_files.keys()))
        for name in sort_paths_recursively(all_files):
            if name in local_files and name in badge_files:
                if local_files[name] == badge_files[name]:
                    status = " "
                else:
                    status = "*"
            elif name in badge_files:
                status = "-"
            elif name in local_files:
                status = "+"
            else:
                status = "?"
            hash = badge_files[name] if name in badge_files else local_files[name]
            if hash == "":
                hash = "directory"
            print(f"{status}      {format_recursive_path(name):<40s} {hash}")

    if args.reset:
        print("Resetting badge...")
        subprocess.run(["mpremote", "reset"], check=True)
