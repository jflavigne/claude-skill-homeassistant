#!/usr/bin/env python3
"""
Home Assistant Automation ID Migration Tool

Safely migrate automation IDs while preserving metadata (area, icon, labels).

The Problem:
When automation YAML `id` is changed:
1. HA creates new entity with `_2` suffix
2. Old metadata (area, icon, labels) is orphaned

Solution - Atomic Migration:
1. Backup registry
2. Stop HA
3. Update YAML files with new IDs
4. Update registry unique_id fields to match
5. Remove orphaned entries
6. Start HA

Usage:
    # Generate migration file from current state
    python3 ha_migrate_automation_ids.py generate > migration.yaml

    # Preview migration
    python3 ha_migrate_automation_ids.py preview migration.yaml

    # Execute migration (full workflow)
    python3 ha_migrate_automation_ids.py execute migration.yaml

    # Fix registry only (after YAML already updated)
    python3 ha_migrate_automation_ids.py fix-registry

Environment Variables Required:
    HASS_SERVER    - Home Assistant server URL
    HASS_TOKEN     - Long-lived access token
    HASS_SSH_HOST  - SSH host (default: homeassistant.local)
    HASS_SSH_USER  - SSH user (default: jflavigne)

Dependencies:
    pip install websockets pyyaml
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml package required. Install with: pip install pyyaml")
    sys.exit(1)

# Import from sibling module
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from ha_backup_registry import backup as backup_registry
except ImportError:
    backup_registry = None


def get_ssh_config():
    """Get SSH configuration from environment."""
    return {
        "host": os.environ.get("HASS_SSH_HOST", "homeassistant.local"),
        "user": os.environ.get("HASS_SSH_USER", "jflavigne"),
    }


def ssh_cmd(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Execute SSH command and return (returncode, stdout, stderr)."""
    config = get_ssh_config()
    full_cmd = f'ssh {config["user"]}@{config["host"]} "{cmd}"'
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


def scp_get(remote_path: str, local_path: str) -> bool:
    """Copy file from HA to local."""
    config = get_ssh_config()
    cmd = f'scp {config["user"]}@{config["host"]}:{remote_path} {local_path}'
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return result.returncode == 0


def scp_put(local_path: str, remote_path: str) -> bool:
    """Copy file from local to HA."""
    config = get_ssh_config()
    cmd = f'scp {local_path} {config["user"]}@{config["host"]}:{remote_path}'
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return result.returncode == 0


def stop_ha() -> bool:
    """Stop Home Assistant via REST API."""
    server = os.environ.get("HASS_SERVER", "http://homeassistant.local:8123")
    token = os.environ.get("HASS_TOKEN")

    if not token:
        print("ERROR: HASS_TOKEN required")
        return False

    import urllib.request
    import urllib.error

    url = f"{server}/api/services/homeassistant/stop"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except urllib.error.URLError as e:
        # Connection refused means HA is already stopping
        if "Connection refused" in str(e):
            return True
        print(f"ERROR stopping HA: {e}")
        return False


def wait_for_ha_stop(max_wait: int = 60) -> bool:
    """Wait for HA to stop."""
    print("Waiting for HA to stop", end="", flush=True)
    for _ in range(max_wait // 2):
        time.sleep(2)
        print(".", end="", flush=True)

        # Check if HA is still responding
        server = os.environ.get("HASS_SERVER", "http://homeassistant.local:8123")
        import urllib.request
        import urllib.error

        try:
            urllib.request.urlopen(f"{server}/api/", timeout=2)
        except urllib.error.URLError:
            # Connection refused = HA stopped
            print(" stopped!")
            return True

    print(" timeout!")
    return False


def reboot_ha() -> bool:
    """Reboot Home Assistant via SSH."""
    print("Rebooting Home Assistant...")
    returncode, _, stderr = ssh_cmd("sudo reboot", timeout=10)
    # reboot command may not return cleanly
    return True


# ============================================================================
# Commands
# ============================================================================


def cmd_generate(args):
    """Generate migration file from current state."""
    # Get registry from HA
    tmp_registry = "/tmp/ha_registry_export.json"
    if not scp_get("/homeassistant/.storage/core.entity_registry", tmp_registry):
        print("ERROR: Could not fetch registry from HA")
        sys.exit(1)

    with open(tmp_registry) as f:
        registry = json.load(f)

    entities = registry["data"]["entities"]
    automations = [e for e in entities if e["entity_id"].startswith("automation.")]

    # Find automations with numeric IDs (candidates for migration)
    migrations = {}
    for entry in automations:
        unique_id = entry["unique_id"]
        entity_id = entry["entity_id"]

        # Skip if already has descriptive ID
        if not unique_id.isdigit():
            continue

        # Suggest new ID based on entity_id
        suggested_id = entity_id.replace("automation.", "")

        migrations[unique_id] = {
            "suggested_new_id": suggested_id,
            "current_entity_id": entity_id,
            "has_metadata": bool(
                entry.get("area_id") or entry.get("icon") or entry.get("labels")
            ),
        }

    # Output as YAML
    print("# Automation ID Migration Plan")
    print("# Generated from current entity registry")
    print("#")
    print("# Edit 'new_id' values as desired, then run:")
    print("#   python3 ha_migrate_automation_ids.py preview <this_file>")
    print("#   python3 ha_migrate_automation_ids.py execute <this_file>")
    print()
    print("migrations:")

    for old_id, info in sorted(migrations.items()):
        print(f"  '{old_id}':")
        print(f"    new_id: {info['suggested_new_id']}")
        print(f"    # entity_id: {info['current_entity_id']}")
        if info["has_metadata"]:
            print(f"    # has_metadata: true (will be preserved)")
        print()

    if not migrations:
        print("  # No automations with numeric IDs found")
        print("  # All automations already have descriptive IDs")


def cmd_preview(args):
    """Preview what the migration would do."""
    with open(args.migration_file) as f:
        config = yaml.safe_load(f)

    migrations = config.get("migrations", {})
    if not migrations:
        print("No migrations defined in config file.")
        return

    # Get current registry
    tmp_registry = "/tmp/ha_registry_preview.json"
    if not scp_get("/homeassistant/.storage/core.entity_registry", tmp_registry):
        print("ERROR: Could not fetch registry from HA")
        sys.exit(1)

    with open(tmp_registry) as f:
        registry = json.load(f)

    entities = registry["data"]["entities"]
    by_unique_id = {e["unique_id"]: e for e in entities}

    print("Migration Preview")
    print("=" * 60)
    print()

    found = 0
    not_found = 0
    with_metadata = 0

    for old_id, new_id_or_config in migrations.items():
        # Handle both simple (old: new) and detailed ({new_id: ...}) formats
        if isinstance(new_id_or_config, dict):
            new_id = new_id_or_config.get("new_id")
        else:
            new_id = new_id_or_config

        entry = by_unique_id.get(str(old_id))

        if entry:
            found += 1
            entity_id = entry["entity_id"]
            meta = []
            if entry.get("area_id"):
                meta.append(f"area={entry['area_id']}")
            if entry.get("icon"):
                meta.append("icon")
            if entry.get("labels"):
                meta.append(f"labels={entry['labels']}")

            if meta:
                with_metadata += 1

            print(f"MIGRATE: {old_id} -> {new_id}")
            print(f"  entity_id: {entity_id}")
            if meta:
                print(f"  metadata: {', '.join(meta)} (will be preserved)")
            print()
        else:
            not_found += 1
            print(f"NOT FOUND: {old_id}")
            print(f"  (may already be migrated)")
            print()

    print("=" * 60)
    print(f"Found: {found}, Not found: {not_found}, With metadata: {with_metadata}")


def cmd_execute(args):
    """Execute the full migration workflow."""
    print("=" * 60)
    print("AUTOMATION ID MIGRATION")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Create local backup of entity registry")
    print("  2. Stop Home Assistant")
    print("  3. Update registry unique_ids")
    print("  4. Reboot Home Assistant")
    print()
    print("IMPORTANT: Update your YAML files FIRST with the new IDs!")
    print()

    confirm = input("Continue? [y/N]: ")
    if confirm.lower() != "y":
        print("Migration cancelled.")
        return

    # Step 1: Backup
    print("\n[1/4] Creating backup...")
    if backup_registry:
        backup_path = backup_registry()
        if not backup_path:
            print("ERROR: Backup failed")
            sys.exit(1)
    else:
        print("WARNING: Backup module not available, skipping backup")

    # Load migration config
    with open(args.migration_file) as f:
        config = yaml.safe_load(f)

    migrations = config.get("migrations", {})
    if not migrations:
        print("ERROR: No migrations defined")
        sys.exit(1)

    # Build lookup: old_id -> new_id
    id_mapping = {}
    for old_id, new_id_or_config in migrations.items():
        if isinstance(new_id_or_config, dict):
            new_id = new_id_or_config.get("new_id")
        else:
            new_id = new_id_or_config
        id_mapping[str(old_id)] = new_id

    # Step 2: Stop HA
    print("\n[2/4] Stopping Home Assistant...")
    if not stop_ha():
        print("ERROR: Could not stop HA")
        sys.exit(1)

    if not wait_for_ha_stop():
        print("WARNING: HA may not have stopped completely")
        confirm = input("Continue anyway? [y/N]: ")
        if confirm.lower() != "y":
            sys.exit(1)

    # Step 3: Update registry
    print("\n[3/4] Updating registry...")
    time.sleep(5)  # Extra wait to ensure HA has written state

    # Fetch registry
    tmp_registry = "/tmp/ha_registry_migrate.json"
    if not scp_get("/homeassistant/.storage/core.entity_registry", tmp_registry):
        print("ERROR: Could not fetch registry")
        sys.exit(1)

    with open(tmp_registry) as f:
        registry = json.load(f)

    entities = registry["data"]["entities"]
    updated = 0

    for entry in entities:
        old_unique_id = entry["unique_id"]
        if old_unique_id in id_mapping:
            new_unique_id = id_mapping[old_unique_id]
            entry["unique_id"] = new_unique_id
            print(f"  {entry['entity_id']}: {old_unique_id} -> {new_unique_id}")
            updated += 1

    print(f"\nUpdated {updated} entries")

    # Save updated registry
    with open(tmp_registry, "w") as f:
        json.dump(registry, f)

    # Upload back to HA
    if not scp_put(tmp_registry, "/tmp/registry_updated.json"):
        print("ERROR: Could not upload registry")
        sys.exit(1)

    returncode, _, stderr = ssh_cmd(
        "sudo mv /tmp/registry_updated.json /homeassistant/.storage/core.entity_registry"
    )
    if returncode != 0:
        print(f"ERROR: Could not move registry: {stderr}")
        sys.exit(1)

    # Step 4: Reboot
    print("\n[4/4] Rebooting Home Assistant...")
    reboot_ha()

    print()
    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print()
    print("Wait 1-2 minutes for HA to start, then verify:")
    print("  - Automations appear without _2 suffix")
    print("  - Metadata (area, icon, labels) preserved")


def cmd_fix_registry(args):
    """Fix registry after YAML IDs already changed (removes _2 duplicates)."""
    print("=" * 60)
    print("FIX REGISTRY (Remove _2 duplicates)")
    print("=" * 60)
    print()
    print("This fixes the registry AFTER you've already updated YAML IDs.")
    print("It will:")
    print("  1. Find entries with _2 suffix")
    print("  2. Update original entry's unique_id to match")
    print("  3. Remove the _2 duplicate")
    print()

    confirm = input("Continue? [y/N]: ")
    if confirm.lower() != "y":
        print("Fix cancelled.")
        return

    # Backup first
    print("\n[1/4] Creating backup...")
    if backup_registry:
        backup_path = backup_registry()
        if not backup_path:
            print("ERROR: Backup failed")
            sys.exit(1)
    else:
        print("WARNING: Backup module not available")

    # Stop HA
    print("\n[2/4] Stopping Home Assistant...")
    if not stop_ha():
        print("ERROR: Could not stop HA")
        sys.exit(1)

    if not wait_for_ha_stop():
        print("WARNING: HA may not have stopped completely")

    time.sleep(5)

    # Fetch and fix registry
    print("\n[3/4] Fixing registry...")
    tmp_registry = "/tmp/ha_registry_fix.json"
    if not scp_get("/homeassistant/.storage/core.entity_registry", tmp_registry):
        print("ERROR: Could not fetch registry")
        sys.exit(1)

    with open(tmp_registry) as f:
        registry = json.load(f)

    entities = registry["data"]["entities"]
    automations = {
        e["entity_id"]: e for e in entities if e["entity_id"].startswith("automation.")
    }

    updated = 0
    removed = 0

    for entity_id, entry in list(automations.items()):
        if entity_id.endswith("_2"):
            base_entity_id = entity_id[:-2]
            if base_entity_id in automations:
                old_entry = automations[base_entity_id]
                new_unique_id = entry["unique_id"]
                old_unique_id = old_entry["unique_id"]

                # Update old entry's unique_id
                old_entry["unique_id"] = new_unique_id
                print(f"  UPDATE: {base_entity_id}")
                print(f"    unique_id: {old_unique_id} -> {new_unique_id}")

                # Show preserved metadata
                meta = []
                if old_entry.get("area_id"):
                    meta.append(f"area={old_entry['area_id']}")
                if old_entry.get("icon"):
                    meta.append("icon")
                if old_entry.get("labels"):
                    meta.append(f"labels={old_entry['labels']}")
                if meta:
                    print(f"    (preserved: {', '.join(meta)})")

                # Remove _2 entry
                entities.remove(entry)
                removed += 1
                updated += 1

    print(f"\nUpdated: {updated}, Removed _2 entries: {removed}")

    # Save
    with open(tmp_registry, "w") as f:
        json.dump(registry, f)

    # Upload
    if not scp_put(tmp_registry, "/tmp/registry_fixed.json"):
        print("ERROR: Could not upload registry")
        sys.exit(1)

    returncode, _, stderr = ssh_cmd(
        "sudo mv /tmp/registry_fixed.json /homeassistant/.storage/core.entity_registry"
    )
    if returncode != 0:
        print(f"ERROR: Could not move registry: {stderr}")
        sys.exit(1)

    # Reboot
    print("\n[4/4] Rebooting Home Assistant...")
    reboot_ha()

    print()
    print("=" * 60)
    print("Fix complete!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Home Assistant Automation ID Migration Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s generate > migration.yaml     Generate migration plan
    %(prog)s preview migration.yaml        Preview what will change
    %(prog)s execute migration.yaml        Run full migration
    %(prog)s fix-registry                  Fix _2 duplicates only
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate command
    subparsers.add_parser(
        "generate",
        help="Generate migration file from current state",
    )

    # preview command
    preview_parser = subparsers.add_parser(
        "preview",
        help="Preview migration changes",
    )
    preview_parser.add_argument("migration_file", help="Migration YAML file")

    # execute command
    execute_parser = subparsers.add_parser(
        "execute",
        help="Execute full migration workflow",
    )
    execute_parser.add_argument("migration_file", help="Migration YAML file")

    # fix-registry command
    subparsers.add_parser(
        "fix-registry",
        help="Fix registry after YAML already updated",
    )

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "preview":
        cmd_preview(args)
    elif args.command == "execute":
        cmd_execute(args)
    elif args.command == "fix-registry":
        cmd_fix_registry(args)


if __name__ == "__main__":
    main()
