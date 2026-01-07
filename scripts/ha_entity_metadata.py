#!/usr/bin/env python3
"""
Home Assistant Entity Metadata Tool

Bulk assign labels, icons, and areas to automations via WebSocket API.
Also manages the label registry (list, create, delete).

Usage:
    # Show statistics (ALWAYS RUN THIS FIRST)
    python3 ha_entity_metadata.py stats

    # Export current metadata to YAML (only automations with metadata)
    python3 ha_entity_metadata.py export > current_metadata.yaml

    # Export ALL automations (including those without metadata)
    python3 ha_entity_metadata.py export --all > all_automations.yaml

    # Apply metadata from config file
    python3 ha_entity_metadata.py apply metadata.yaml

    # Dry-run to preview changes
    python3 ha_entity_metadata.py apply metadata.yaml --dry-run

    # Set single automation
    python3 ha_entity_metadata.py set automation.kitchen_thermostat \
        --icon mdi:thermometer --area kitchen --labels thermostat,climate

    # Label management
    python3 ha_entity_metadata.py labels list
    python3 ha_entity_metadata.py labels create climate --icon mdi:thermometer --color blue
    python3 ha_entity_metadata.py labels delete climate

Environment Variables Required:
    HASS_SERVER - Home Assistant server URL (e.g., http://homeassistant.local:8123)
    HASS_TOKEN  - Long-lived access token

Dependencies:
    pip install websockets pyyaml
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

try:
    import websockets
except ImportError:
    print("ERROR: websockets package required. Install with: pip install websockets")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml package required. Install with: pip install pyyaml")
    sys.exit(1)


@dataclass
class HAConnection:
    """Home Assistant WebSocket connection."""

    ws: Any
    msg_id: int = 0

    def next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    async def send(self, msg_type: str, **kwargs) -> dict:
        """Send a message and wait for response."""
        msg_id = self.next_id()
        msg = {"id": msg_id, "type": msg_type, **kwargs}
        await self.ws.send(json.dumps(msg))

        while True:
            response = json.loads(await self.ws.recv())
            if response.get("id") == msg_id:
                return response
            # Handle events or other messages
            if response.get("type") == "event":
                continue


async def connect() -> HAConnection:
    """Connect to Home Assistant WebSocket API."""
    server = os.environ.get("HASS_SERVER", "http://homeassistant.local:8123")
    token = os.environ.get("HASS_TOKEN")

    if not token:
        raise ValueError("HASS_TOKEN environment variable required")

    # Convert http(s) to ws(s)
    ws_url = server.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/websocket"

    ws = await websockets.connect(ws_url)

    # Wait for auth_required
    msg = json.loads(await ws.recv())
    if msg.get("type") != "auth_required":
        raise ValueError(f"Unexpected message: {msg}")

    # Send auth
    await ws.send(json.dumps({"type": "auth", "access_token": token}))

    # Wait for auth_ok
    msg = json.loads(await ws.recv())
    if msg.get("type") != "auth_ok":
        raise ValueError(f"Authentication failed: {msg}")

    return HAConnection(ws=ws)


async def get_entity_registry(conn: HAConnection) -> list[dict]:
    """Get all entities from registry."""
    response = await conn.send("config/entity_registry/list")
    if not response.get("success"):
        raise ValueError(f"Failed to get entity registry: {response}")
    return response.get("result", [])


async def get_area_registry(conn: HAConnection) -> dict[str, str]:
    """Get area registry as {area_id: area_name}."""
    response = await conn.send("config/area_registry/list")
    if not response.get("success"):
        raise ValueError(f"Failed to get area registry: {response}")
    return {a["area_id"]: a["name"] for a in response.get("result", [])}


async def get_label_registry(conn: HAConnection) -> list[dict]:
    """Get all labels."""
    response = await conn.send("config/label_registry/list")
    if not response.get("success"):
        raise ValueError(f"Failed to get label registry: {response}")
    return response.get("result", [])


async def update_entity(
    conn: HAConnection,
    entity_id: str,
    icon: str | None = None,
    area_id: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """Update entity metadata."""
    kwargs = {"entity_id": entity_id}
    if icon is not None:
        kwargs["icon"] = icon
    if area_id is not None:
        kwargs["area_id"] = area_id
    if labels is not None:
        kwargs["labels"] = labels

    response = await conn.send("config/entity_registry/update", **kwargs)
    return response


async def create_label(
    conn: HAConnection,
    name: str,
    icon: str | None = None,
    color: str | None = None,
) -> dict:
    """Create a new label."""
    kwargs = {"name": name}
    if icon:
        kwargs["icon"] = icon
    if color:
        kwargs["color"] = color

    response = await conn.send("config/label_registry/create", **kwargs)
    return response


async def delete_label(conn: HAConnection, label_id: str) -> dict:
    """Delete a label."""
    response = await conn.send("config/label_registry/delete", label_id=label_id)
    return response


# ============================================================================
# Commands
# ============================================================================


async def cmd_stats(args):
    """Show statistics about automation metadata coverage."""
    conn = await connect()

    try:
        entities = await get_entity_registry(conn)
        areas = await get_area_registry(conn)

        automations = [e for e in entities if e["entity_id"].startswith("automation.")]

        total = len(automations)
        with_area = len([a for a in automations if a.get("area_id")])
        with_icon = len([a for a in automations if a.get("icon")])
        with_labels = len([a for a in automations if a.get("labels")])

        print("Automation Metadata Statistics")
        print("=" * 50)
        print(f"Total automations: {total}")
        print()
        print(f"With area:   {with_area:>4}/{total} ({100*with_area//total if total else 0}%)")
        print(f"With icon:   {with_icon:>4}/{total} ({100*with_icon//total if total else 0}%)")
        print(f"With labels: {with_labels:>4}/{total} ({100*with_labels//total if total else 0}%)")
        print()

        # Show breakdown by area
        area_counts = {}
        no_area = []
        for a in automations:
            area_id = a.get("area_id")
            if area_id:
                area_name = areas.get(area_id, area_id)
                area_counts[area_name] = area_counts.get(area_name, 0) + 1
            else:
                no_area.append(a["entity_id"])

        if area_counts:
            print("By Area:")
            print("-" * 50)
            for area_name, count in sorted(area_counts.items(), key=lambda x: -x[1]):
                print(f"  {area_name:<25} {count:>4}")
            if no_area:
                print(f"  {'(no area)':<25} {len(no_area):>4}")
        print()

        # Show automations without area (if any)
        if no_area and len(no_area) <= 20:
            print("Automations missing area:")
            print("-" * 50)
            for entity_id in sorted(no_area):
                print(f"  {entity_id}")
        elif no_area:
            print(f"Automations missing area: {len(no_area)} (use 'export --all' to see them)")

    finally:
        await conn.ws.close()


async def cmd_export(args):
    """Export current automation metadata to YAML."""
    conn = await connect()

    try:
        entities = await get_entity_registry(conn)
        areas = await get_area_registry(conn)

        # Filter to automations
        automations = {}
        for entity in entities:
            if not entity["entity_id"].startswith("automation."):
                continue

            meta = {}
            if entity.get("icon"):
                meta["icon"] = entity["icon"]
            if entity.get("area_id"):
                meta["area_id"] = entity["area_id"]
                meta["area_name"] = areas.get(entity["area_id"], "unknown")
            if entity.get("labels"):
                meta["labels"] = entity["labels"]

            # Include if has metadata OR if --all flag is set
            if meta or args.all:
                automations[entity["entity_id"]] = meta

        # Custom YAML output for cleaner formatting
        print("# Home Assistant Automation Metadata")
        print("# Exported:", __import__("datetime").datetime.now().isoformat())
        if args.all:
            print("# Mode: ALL automations (including those without metadata)")
        else:
            print("# Mode: Only automations with existing metadata")
            print("# Tip: Use --all to export ALL automations")
        print("#")
        print("# Usage: python3 ha_entity_metadata.py apply <this_file>")
        print()
        print("automations:")
        for entity_id, meta in sorted(automations.items()):
            print(f"  {entity_id}:")
            if meta:
                if "icon" in meta:
                    print(f"    icon: {meta['icon']}")
                if "area_id" in meta:
                    print(f"    area_id: {meta['area_id']}  # {meta.get('area_name', '')}")
                if "labels" in meta:
                    print(f"    labels: {meta['labels']}")
            else:
                print(f"    # TODO: Add area_id, icon, labels")
            print()

    finally:
        await conn.ws.close()


async def cmd_apply(args):
    """Apply metadata from YAML file."""
    with open(args.config_file) as f:
        config = yaml.safe_load(f)

    automations = config.get("automations", {})
    if not automations:
        print("No automations found in config file.")
        return

    conn = await connect()

    try:
        # Get existing labels to validate
        existing_labels = await get_label_registry(conn)
        label_ids = {label["label_id"] for label in existing_labels}

        # Track results
        success_count = 0
        error_count = 0
        skipped_count = 0

        for entity_id, meta in automations.items():
            # Validate labels exist
            if "labels" in meta:
                missing_labels = [l for l in meta["labels"] if l not in label_ids]
                if missing_labels:
                    print(f"WARNING: {entity_id} - missing labels: {missing_labels}")
                    print(f"  Create them first: python3 ha_entity_metadata.py labels create <name>")
                    if not args.dry_run:
                        error_count += 1
                        continue

            if args.dry_run:
                print(f"[DRY-RUN] Would update {entity_id}:")
                if "icon" in meta:
                    print(f"  icon: {meta['icon']}")
                if "area_id" in meta:
                    print(f"  area_id: {meta['area_id']}")
                if "labels" in meta:
                    print(f"  labels: {meta['labels']}")
                skipped_count += 1
            else:
                response = await update_entity(
                    conn,
                    entity_id,
                    icon=meta.get("icon"),
                    area_id=meta.get("area_id"),
                    labels=meta.get("labels"),
                )

                if response.get("success"):
                    print(f"OK: {entity_id}")
                    success_count += 1
                else:
                    print(f"ERROR: {entity_id} - {response.get('error', {}).get('message', 'unknown')}")
                    error_count += 1

        print()
        if args.dry_run:
            print(f"Dry run complete. Would update {skipped_count} automation(s).")
        else:
            print(f"Complete. Success: {success_count}, Errors: {error_count}")

    finally:
        await conn.ws.close()


async def cmd_set(args):
    """Set metadata for a single automation."""
    if not any([args.icon, args.area, args.labels]):
        print("ERROR: At least one of --icon, --area, or --labels required")
        sys.exit(1)

    labels = args.labels.split(",") if args.labels else None

    conn = await connect()

    try:
        # Validate labels exist
        if labels:
            existing_labels = await get_label_registry(conn)
            label_ids = {label["label_id"] for label in existing_labels}
            missing = [l for l in labels if l not in label_ids]
            if missing:
                print(f"ERROR: Labels don't exist: {missing}")
                print(f"Create them first: python3 ha_entity_metadata.py labels create <name>")
                sys.exit(1)

        response = await update_entity(
            conn,
            args.entity_id,
            icon=args.icon,
            area_id=args.area,
            labels=labels,
        )

        if response.get("success"):
            print(f"Updated {args.entity_id}")
            result = response.get("result", {})
            if result.get("icon"):
                print(f"  icon: {result['icon']}")
            if result.get("area_id"):
                print(f"  area_id: {result['area_id']}")
            if result.get("labels"):
                print(f"  labels: {result['labels']}")
        else:
            print(f"ERROR: {response.get('error', {}).get('message', 'unknown')}")
            sys.exit(1)

    finally:
        await conn.ws.close()


async def cmd_labels_list(args):
    """List all labels."""
    conn = await connect()

    try:
        labels = await get_label_registry(conn)

        if not labels:
            print("No labels defined.")
            return

        print(f"Labels ({len(labels)}):\n")
        print(f"{'ID':<25} {'Name':<20} {'Icon':<25} {'Color':<10}")
        print("-" * 80)

        for label in sorted(labels, key=lambda x: x.get("name", "")):
            label_id = label.get('label_id', '') or ''
            name = label.get('name', '') or ''
            icon = label.get('icon', '') or ''
            color = label.get('color', '') or ''
            print(f"{label_id:<25} {name:<20} {icon:<25} {color:<10}")

    finally:
        await conn.ws.close()


async def cmd_labels_create(args):
    """Create a new label."""
    conn = await connect()

    try:
        response = await create_label(conn, args.name, args.icon, args.color)

        if response.get("success"):
            result = response.get("result", {})
            print(f"Created label: {result.get('label_id', args.name)}")
            if args.icon:
                print(f"  icon: {args.icon}")
            if args.color:
                print(f"  color: {args.color}")
        else:
            error = response.get("error", {})
            print(f"ERROR: {error.get('message', 'unknown')}")
            sys.exit(1)

    finally:
        await conn.ws.close()


async def cmd_labels_delete(args):
    """Delete a label."""
    conn = await connect()

    try:
        response = await delete_label(conn, args.label_id)

        if response.get("success"):
            print(f"Deleted label: {args.label_id}")
        else:
            error = response.get("error", {})
            print(f"ERROR: {error.get('message', 'unknown')}")
            sys.exit(1)

    finally:
        await conn.ws.close()


async def cmd_labels_suggest(args):
    """Suggest which automations would match a label pattern."""
    import fnmatch

    conn = await connect()

    try:
        entities = await get_entity_registry(conn)

        matches = []
        for entity in entities:
            entity_id = entity["entity_id"]
            if not entity_id.startswith("automation."):
                continue
            if fnmatch.fnmatch(entity_id, args.pattern):
                matches.append(entity_id)

        if matches:
            print(f"Automations matching '{args.pattern}':\n")
            for entity_id in sorted(matches):
                print(f"  {entity_id}")
            print(f"\n{len(matches)} automation(s) would receive label '{args.label_name}'")
        else:
            print(f"No automations match pattern '{args.pattern}'")

    finally:
        await conn.ws.close()


def main():
    parser = argparse.ArgumentParser(
        description="Home Assistant Entity Metadata Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats command
    subparsers.add_parser(
        "stats",
        help="Show statistics about automation metadata coverage (run this first!)",
    )

    # export command
    export_parser = subparsers.add_parser(
        "export",
        help="Export current automation metadata to YAML",
    )
    export_parser.add_argument(
        "--all",
        action="store_true",
        help="Export ALL automations, not just those with metadata",
    )

    # apply command
    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply metadata from YAML config file",
    )
    apply_parser.add_argument("config_file", help="YAML config file")
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )

    # set command
    set_parser = subparsers.add_parser(
        "set",
        help="Set metadata for single automation",
    )
    set_parser.add_argument("entity_id", help="Automation entity ID")
    set_parser.add_argument("--icon", help="Icon (e.g., mdi:thermometer)")
    set_parser.add_argument("--area", help="Area ID")
    set_parser.add_argument("--labels", help="Comma-separated labels")

    # labels subcommand
    labels_parser = subparsers.add_parser("labels", help="Label management")
    labels_sub = labels_parser.add_subparsers(dest="labels_command", required=True)

    # labels list
    labels_sub.add_parser("list", help="List all labels")

    # labels create
    labels_create = labels_sub.add_parser("create", help="Create a new label")
    labels_create.add_argument("name", help="Label name")
    labels_create.add_argument("--icon", help="Icon (e.g., mdi:thermometer)")
    labels_create.add_argument("--color", help="Color name")

    # labels delete
    labels_delete = labels_sub.add_parser("delete", help="Delete a label")
    labels_delete.add_argument("label_id", help="Label ID to delete")

    # labels suggest
    labels_suggest = labels_sub.add_parser(
        "suggest",
        help="Show automations matching a pattern",
    )
    labels_suggest.add_argument("label_name", help="Proposed label name")
    labels_suggest.add_argument(
        "--pattern",
        required=True,
        help="Glob pattern (e.g., 'automation.*thermostat*')",
    )

    args = parser.parse_args()

    # Route to appropriate command
    if args.command == "stats":
        asyncio.run(cmd_stats(args))
    elif args.command == "export":
        asyncio.run(cmd_export(args))
    elif args.command == "apply":
        asyncio.run(cmd_apply(args))
    elif args.command == "set":
        asyncio.run(cmd_set(args))
    elif args.command == "labels":
        if args.labels_command == "list":
            asyncio.run(cmd_labels_list(args))
        elif args.labels_command == "create":
            asyncio.run(cmd_labels_create(args))
        elif args.labels_command == "delete":
            asyncio.run(cmd_labels_delete(args))
        elif args.labels_command == "suggest":
            asyncio.run(cmd_labels_suggest(args))


if __name__ == "__main__":
    main()
