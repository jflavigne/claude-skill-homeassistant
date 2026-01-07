#!/usr/bin/env python3
"""
Home Assistant Entity Registry Backup Tool

Creates timestamped backups of the entity registry before making changes.
Backups are stored locally and can be restored via SSH.

Usage:
    # Create backup
    python3 ha_backup_registry.py backup

    # List existing backups
    python3 ha_backup_registry.py list

    # Restore from backup
    python3 ha_backup_registry.py restore 20260107_120000

    # Clean old backups (keep last N)
    python3 ha_backup_registry.py clean --keep 5

Environment Variables Required:
    HASS_SSH_HOST - Home Assistant host (default: homeassistant.local)
    HASS_SSH_USER - SSH username (default: jflavigne)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
BACKUP_DIR = Path(__file__).parent / "backups"
REMOTE_REGISTRY = "/homeassistant/.storage/core.entity_registry"
DEFAULT_KEEP = 10


def get_ssh_config():
    """Get SSH configuration from environment."""
    return {
        "host": os.environ.get("HASS_SSH_HOST", "homeassistant.local"),
        "user": os.environ.get("HASS_SSH_USER", "jflavigne"),
    }


def ssh_cmd(cmd: str) -> tuple[int, str, str]:
    """Execute SSH command and return (returncode, stdout, stderr)."""
    config = get_ssh_config()
    full_cmd = f'ssh {config["user"]}@{config["host"]} "{cmd}"'
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def backup() -> Path | None:
    """Create a backup of the entity registry."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"entity_registry.{timestamp}.json"

    print(f"Fetching registry from Home Assistant...")
    config = get_ssh_config()

    # Use scp to fetch the file
    scp_cmd = f'scp {config["user"]}@{config["host"]}:{REMOTE_REGISTRY} {backup_path}'
    result = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to fetch registry")
        print(f"  {result.stderr}")
        return None

    # Verify JSON integrity
    try:
        with open(backup_path) as f:
            data = json.load(f)
        entity_count = len(data.get("data", {}).get("entities", []))
        print(f"Backup created: {backup_path.name}")
        print(f"  Entities: {entity_count}")
        print(f"  Size: {backup_path.stat().st_size:,} bytes")
        return backup_path
    except json.JSONDecodeError as e:
        print(f"ERROR: Backup file is not valid JSON")
        print(f"  {e}")
        backup_path.unlink()
        return None


def list_backups() -> list[Path]:
    """List all available backups."""
    if not BACKUP_DIR.exists():
        print("No backups directory found.")
        return []

    backups = sorted(BACKUP_DIR.glob("entity_registry.*.json"), reverse=True)

    if not backups:
        print("No backups found.")
        return []

    print(f"Available backups ({len(backups)}):\n")
    print(f"{'Timestamp':<20} {'Entities':<10} {'Size':<12}")
    print("-" * 42)

    for backup_path in backups:
        # Extract timestamp from filename
        ts = backup_path.stem.split(".", 1)[1]

        # Get entity count
        try:
            with open(backup_path) as f:
                data = json.load(f)
            entity_count = len(data.get("data", {}).get("entities", []))
        except (json.JSONDecodeError, KeyError):
            entity_count = "invalid"

        size = f"{backup_path.stat().st_size:,}"
        print(f"{ts:<20} {str(entity_count):<10} {size:<12}")

    return backups


def restore(timestamp: str) -> bool:
    """Restore a backup to Home Assistant."""
    backup_path = BACKUP_DIR / f"entity_registry.{timestamp}.json"

    if not backup_path.exists():
        print(f"ERROR: Backup not found: {backup_path.name}")
        print("Use 'list' command to see available backups.")
        return False

    # Verify JSON integrity before restore
    try:
        with open(backup_path) as f:
            data = json.load(f)
        entity_count = len(data.get("data", {}).get("entities", []))
    except json.JSONDecodeError as e:
        print(f"ERROR: Backup file is corrupted")
        print(f"  {e}")
        return False

    print(f"Restoring backup: {backup_path.name}")
    print(f"  Entities: {entity_count}")
    print()
    print("WARNING: Home Assistant should be STOPPED before restoring!")
    print("  1. Stop HA: curl -X POST 'http://homeassistant.local:8123/api/services/homeassistant/stop' -H 'Authorization: Bearer $HASS_TOKEN'")
    print("  2. Wait 15 seconds")
    print("  3. Run this restore command")
    print("  4. Reboot HA: ssh user@homeassistant.local 'sudo reboot'")
    print()

    confirm = input("Continue with restore? [y/N]: ")
    if confirm.lower() != "y":
        print("Restore cancelled.")
        return False

    config = get_ssh_config()

    # Create backup on remote before overwriting
    print("Creating remote backup before restore...")
    remote_backup = f"{REMOTE_REGISTRY}.pre_restore.{timestamp}"
    returncode, _, stderr = ssh_cmd(f"sudo cp {REMOTE_REGISTRY} {remote_backup}")
    if returncode != 0:
        print(f"WARNING: Could not create remote backup: {stderr}")

    # Upload the backup file
    print("Uploading backup...")
    scp_cmd = f'scp {backup_path} {config["user"]}@{config["host"]}:/tmp/registry_restore.json'
    result = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to upload backup")
        print(f"  {result.stderr}")
        return False

    # Move to final location with sudo
    returncode, _, stderr = ssh_cmd(
        f"sudo mv /tmp/registry_restore.json {REMOTE_REGISTRY}"
    )

    if returncode != 0:
        print(f"ERROR: Failed to restore registry")
        print(f"  {stderr}")
        return False

    print("Restore complete!")
    print("Now reboot Home Assistant to apply changes.")
    return True


def clean(keep: int = DEFAULT_KEEP) -> int:
    """Remove old backups, keeping the most recent N."""
    if not BACKUP_DIR.exists():
        print("No backups directory found.")
        return 0

    backups = sorted(BACKUP_DIR.glob("entity_registry.*.json"), reverse=True)

    if len(backups) <= keep:
        print(f"Only {len(backups)} backups exist, keeping all (threshold: {keep}).")
        return 0

    to_remove = backups[keep:]
    removed = 0

    for backup_path in to_remove:
        try:
            backup_path.unlink()
            print(f"Removed: {backup_path.name}")
            removed += 1
        except OSError as e:
            print(f"ERROR: Could not remove {backup_path.name}: {e}")

    print(f"\nRemoved {removed} old backup(s), kept {keep} most recent.")
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Home Assistant Entity Registry Backup Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s backup              Create a new backup
    %(prog)s list                List all backups
    %(prog)s restore 20260107    Restore specific backup
    %(prog)s clean --keep 5      Keep only 5 most recent backups
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # backup command
    subparsers.add_parser("backup", help="Create a new backup")

    # list command
    subparsers.add_parser("list", help="List available backups")

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Restore a backup")
    restore_parser.add_argument(
        "timestamp",
        help="Backup timestamp (from list command)",
    )

    # clean command
    clean_parser = subparsers.add_parser("clean", help="Remove old backups")
    clean_parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"Number of backups to keep (default: {DEFAULT_KEEP})",
    )

    args = parser.parse_args()

    if args.command == "backup":
        result = backup()
        sys.exit(0 if result else 1)
    elif args.command == "list":
        list_backups()
    elif args.command == "restore":
        success = restore(args.timestamp)
        sys.exit(0 if success else 1)
    elif args.command == "clean":
        clean(args.keep)


if __name__ == "__main__":
    main()
