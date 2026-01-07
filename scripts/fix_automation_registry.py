#!/usr/bin/env python3
"""
Fix automation entity registry after changing automation IDs.

Problem: When automation YAML `id` fields are changed, HA creates new entity
registry entries with `_2` suffixes, orphaning the old entries (which have
the metadata like area, icon, labels).

Solution: Update the `unique_id` in old entries to match new YAML IDs,
preserving metadata, then delete the duplicate `_2` entries.

IMPORTANT: Run this while HA is STOPPED, not just restarted!

Usage:
    # 1. Stop HA
    curl -X POST "http://homeassistant.local:8123/api/services/homeassistant/stop" \
      -H "Authorization: Bearer $HASS_TOKEN"

    # 2. Wait for HA to stop
    sleep 15

    # 3. Run this script on HA
    ssh user@homeassistant.local "sudo python3 /path/to/fix_automation_registry.py"

    # 4. Reboot to start HA
    ssh user@homeassistant.local "sudo reboot"
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path("/homeassistant/.storage/core.entity_registry")


def main():
    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = REGISTRY_PATH.with_suffix(f".backup.{ts}")
    shutil.copy(REGISTRY_PATH, backup_path)
    print(f"Backup: {backup_path}")

    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    entities = registry["data"]["entities"]
    automations = {
        e["entity_id"]: e
        for e in entities
        if e["entity_id"].startswith("automation.")
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

                # Update old entry's unique_id to match new YAML id
                old_entry["unique_id"] = new_unique_id
                print(f"UPDATE: {base_entity_id}")
                print(f"  unique_id: {old_unique_id} -> {new_unique_id}")

                # Show preserved metadata
                meta = []
                if old_entry.get("area_id"):
                    meta.append(f"area={old_entry['area_id']}")
                if old_entry.get("icon"):
                    meta.append("icon=yes")
                if old_entry.get("labels"):
                    meta.append(f"labels={old_entry['labels']}")
                if meta:
                    print(f"  (preserved: {', '.join(meta)})")

                # Remove _2 entry
                entities.remove(entry)
                removed += 1
                updated += 1

    print(f"\nUpdated: {updated}, Removed _2 entries: {removed}")

    # Save
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f)

    print("Done! Start HA now.")


if __name__ == "__main__":
    main()
