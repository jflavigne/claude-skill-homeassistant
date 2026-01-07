---
name: home-assistant-manager
description: Expert-level Home Assistant configuration management with efficient deployment workflows (git and rapid scp iteration), remote CLI access via SSH and hass-cli, automation verification protocols, log analysis, reload vs restart optimization, and comprehensive Lovelace dashboard management for tablet-optimized UIs. Includes template patterns, card types, debugging strategies, and real-world examples.
---

# Home Assistant Manager

Expert-level Home Assistant configuration management with efficient workflows, remote CLI access, and verification protocols.

## Core Capabilities

- Remote Home Assistant instance management via SSH and hass-cli
- Smart deployment workflows (git-based and rapid iteration)
- Configuration validation and safety checks
- Automation testing and verification
- Log analysis and error detection
- Reload vs restart optimization
- Lovelace dashboard development and optimization
- Template syntax patterns and debugging
- Tablet-optimized UI design

## Prerequisites

Before starting, verify the environment has:
1. SSH access to Home Assistant instance (`jflavigne@homeassistant.local`)
2. `hass-cli` installed locally
3. Environment variables loaded (HASS_SERVER, HASS_TOKEN) - via `source .env`
4. Git repository connected to HA `/homeassistant` directory
5. Context7 MCP server with Home Assistant docs (optional)

**Note:** The `ha core` CLI commands are not available via the SSH add-on. Use `hass-cli` for service calls and API access instead.

## Quick Deployment (Claude Code)

Two methods available for deploying config changes from Claude Code:

### Method 1: SSH + tar (Direct, Always Works)
```bash
# Deploy all config files
tar czf - automations.yaml scripts.yaml templates/ | ssh jflavigne@homeassistant.local "cd /homeassistant && sudo tar xzf -"

# Reload via hass-cli
export HASS_SERVER=http://homeassistant.local:8123
export HASS_TOKEN=<token_from_.envrc>
hass-cli service call automation.reload
hass-cli service call script.reload
hass-cli service call template.reload
```

### Method 2: MCP Script (After Git SSH Setup)
Once git SSH is configured on HA, call via MCP:
```
script.deploy_from_github
```
This pulls from GitHub and reloads all YAML automatically.

### Environment Setup
Source credentials before using hass-cli:
```bash
export HASS_SERVER=http://homeassistant.local:8123
export HASS_TOKEN=<from .envrc>
export HASS_SSH_USER=jflavigne
export HASS_SSH_HOST=homeassistant.local
```

## Remote Access Patterns

### Using hass-cli (Local, via REST API)

All `hass-cli` commands use environment variables automatically:

```bash
# List entities
hass-cli state list

# Get specific state
hass-cli state get sensor.entity_name

# Call services
hass-cli service call automation.reload
hass-cli service call automation.trigger --arguments entity_id=automation.name
```

### Using SSH for File Operations

```bash
# Deploy files via SCP
scp automations.yaml jflavigne@homeassistant.local:/homeassistant/

# Pull latest from git
ssh jflavigne@homeassistant.local "cd /homeassistant && git pull"

# Check git status on HA
ssh jflavigne@homeassistant.local "cd /homeassistant && git status"
```

**Note:** `ha core check/restart/logs` commands require Supervisor access (not available via SSH add-on). Use hass-cli instead:
```bash
# Reload automations (instead of restart)
hass-cli service call automation.reload

# Check for errors via API
hass-cli raw get /api/error/all
```

## Deployment Workflows

### Standard Git Workflow (Final Changes)

Use for changes you want in version control:

```bash
# 1. Make changes locally
# 2. Check validity
ssh jflavigne@homeassistant.local "ha core check"

# 3. Commit and push
git add file.yaml
git commit -m "Description"
git push

# 4. CRITICAL: Pull to HA instance
ssh jflavigne@homeassistant.local "cd /homeassistant && git pull"

# 5. Reload or restart
hass-cli service call automation.reload  # if reload sufficient
# OR
ssh jflavigne@homeassistant.local "ha core restart"  # if restart needed

# 6. Verify
hass-cli state get sensor.new_entity
ssh jflavigne@homeassistant.local "ha core logs | grep -i error | tail -20"
```

### Rapid Development Workflow (Testing/Iteration)

Use `scp` for quick testing before committing:

```bash
# 1. Make changes locally
# 2. Quick deploy
scp automations.yaml jflavigne@homeassistant.local:/homeassistant/

# 3. Reload/restart
hass-cli service call automation.reload

# 4. Test and iterate (repeat 1-3 as needed)

# 5. Once finalized, commit to git
git add automations.yaml
git commit -m "Final tested changes"
git push
```

**When to use scp:**
- 🚀 Rapid iteration and testing
- 🔄 Frequent small adjustments
- 🧪 Experimental changes
- 🎨 UI/Dashboard work

**When to use git:**
- ✅ Final tested changes
- 📦 Version control tracking
- 🔒 Important configs
- 👥 Changes to document

## Reload vs Restart Decision Making

**ALWAYS assess if reload is sufficient before requiring a full restart.**

### Can be reloaded (fast, preferred):
- ✅ Automations: `hass-cli service call automation.reload`
- ✅ Scripts: `hass-cli service call script.reload`
- ✅ Scenes: `hass-cli service call scene.reload`
- ✅ Template entities: `hass-cli service call template.reload`
- ✅ Groups: `hass-cli service call group.reload`
- ✅ Themes: `hass-cli service call frontend.reload_themes`

### Require full restart:
- ❌ Min/Max sensors and platform-based sensors
- ❌ New integrations in configuration.yaml
- ❌ Core configuration changes
- ❌ MQTT sensor/binary_sensor platforms

## Automation Verification Workflow

**ALWAYS verify automations after deployment:**

### Step 1: Deploy
```bash
git add automations.yaml && git commit -m "..." && git push
ssh jflavigne@homeassistant.local "cd /homeassistant && git pull"
```

### Step 2: Check Configuration
```bash
ssh jflavigne@homeassistant.local "ha core check"
```

### Step 3: Reload
```bash
hass-cli service call automation.reload
```

### Step 4: Manually Trigger
```bash
hass-cli service call automation.trigger --arguments entity_id=automation.name
```

**Why trigger manually?**
- Instant feedback (don't wait for scheduled triggers)
- Verify logic before production
- Catch errors immediately

### Step 5: Check Logs
```bash
sleep 3
ssh jflavigne@homeassistant.local "ha core logs | grep -i 'automation_name' | tail -20"
```

**Success indicators:**
- `Initialized trigger AutomationName`
- `Running automation actions`
- `Executing step ...`
- No ERROR or WARNING messages

**Error indicators:**
- `Error executing script`
- `Invalid data for call_service`
- `TypeError`, `Template variable warning`

### Step 6: Verify Outcome

**For notifications:**
- Ask user if they received it
- Check logs for mobile_app messages

**For device control:**
```bash
hass-cli state get switch.device_name
```

**For sensors:**
```bash
hass-cli state get sensor.new_sensor
```

### Step 7: Fix and Re-test if Needed
If errors found:
1. Identify root cause from error messages
2. Fix the issue
3. Re-deploy (steps 1-2)
4. Re-verify (steps 3-6)

## Dashboard Management

### Dashboard Fundamentals

**What are Lovelace Dashboards?**
- JSON files in `.storage/` directory (e.g., `.storage/lovelace.control_center`)
- UI configuration for Home Assistant frontend
- Optimizable for different devices (mobile, tablet, wall panels)

**Critical Understanding:**
- Creating dashboard file is NOT enough - must register in `.storage/lovelace_dashboards`
- Dashboard changes don't require HA restart (just browser refresh)
- Use panel view for full-screen content (maps, cameras)
- Use sections view for organized multi-card layouts

### Dashboard Development Workflow

**Rapid Iteration with scp (Recommended for dashboards):**

```bash
# 1. Make changes locally
vim .storage/lovelace.control_center

# 2. Deploy immediately (no git commit yet)
scp .storage/lovelace.control_center jflavigne@homeassistant.local:/homeassistant/.storage/

# 3. Refresh browser (Ctrl+F5 or Cmd+Shift+R)
# No HA restart needed!

# 4. Iterate: Repeat 1-3 until perfect

# 5. Commit when stable
git add .storage/lovelace.control_center
git commit -m "Update dashboard layout"
git push
ssh jflavigne@homeassistant.local "cd /homeassistant && git pull"
```

**Why scp for dashboards:**
- Instant feedback (no HA restart)
- Iterate quickly on visual changes
- Commit only stable versions

### Creating New Dashboard

**Complete workflow:**

```bash
# Step 1: Create dashboard file
cp .storage/lovelace.my_home .storage/lovelace.new_dashboard

# Step 2: Register in lovelace_dashboards
# Edit .storage/lovelace_dashboards to add:
{
  "id": "new_dashboard",
  "show_in_sidebar": true,
  "icon": "mdi:tablet-dashboard",
  "title": "New Dashboard",
  "require_admin": false,
  "mode": "storage",
  "url_path": "new-dashboard"
}

# Step 3: Deploy both files
scp .storage/lovelace.new_dashboard jflavigne@homeassistant.local:/homeassistant/.storage/
scp .storage/lovelace_dashboards jflavigne@homeassistant.local:/homeassistant/.storage/

# Step 4: Restart HA (required for registry changes)
ssh jflavigne@homeassistant.local "ha core restart"
sleep 30

# Step 5: Verify appears in sidebar
```

**Update .gitignore to track:**
```gitignore
# Exclude .storage/ by default
.storage/

# Include dashboard files
!.storage/lovelace.new_dashboard
!.storage/lovelace_dashboards
```

### View Types Decision Matrix

**Use Panel View when:**
- Displaying full-screen map (vacuum, cameras)
- Single large card needs full width
- Want zero margins/padding
- Minimize scrolling

**Use Sections View when:**
- Organizing multiple cards
- Need responsive grid layout
- Building multi-section dashboards

**Layout Example:**
```json
// Panel view - full width, no margins
{
  "type": "panel",
  "title": "Vacuum Map",
  "path": "map",
  "cards": [
    {
      "type": "custom:xiaomi-vacuum-map-card",
      "entity": "vacuum.dusty"
    }
  ]
}

// Sections view - organized, has ~10% margins
{
  "type": "sections",
  "title": "Home",
  "sections": [
    {
      "type": "grid",
      "cards": [...]
    }
  ]
}
```

### Card Types Quick Reference

**Mushroom Cards (Modern, Touch-Optimized):**
```json
{
  "type": "custom:mushroom-light-card",
  "entity": "light.living_room",
  "use_light_color": true,
  "show_brightness_control": true,
  "collapsible_controls": true,
  "fill_container": true
}
```
- Best for tablets and touch screens
- Animated, colorful icons
- Built-in slider controls

**Mushroom Template Card (Dynamic Content):**
```json
{
  "type": "custom:mushroom-template-card",
  "primary": "All Doors",
  "secondary": "{% set sensors = ['binary_sensor.front_door'] %}\n{% set open = sensors | select('is_state', 'on') | list | length %}\n{{ open }} / {{ sensors | length }} open",
  "icon": "mdi:door",
  "icon_color": "{% if open > 0 %}red{% else %}green{% endif %}"
}
```
- Use Jinja2 templates for dynamic content
- Color-code status with icon_color
- Multi-line templates use `\n` in JSON

**Tile Card (Built-in, Modern):**
```json
{
  "type": "tile",
  "entity": "climate.thermostat",
  "features": [
    {"type": "climate-hvac-modes", "hvac_modes": ["heat", "cool", "fan_only", "off"]},
    {"type": "target-temperature"}
  ]
}
```
- No custom cards required
- Built-in features for controls

### Common Template Patterns

**Counting Open Doors:**
```jinja2
{% set door_sensors = [
  'binary_sensor.front_door',
  'binary_sensor.back_door'
] %}
{% set open = door_sensors | select('is_state', 'on') | list | length %}
{{ open }} / {{ door_sensors | length }} open
```

**Color-Coded Days Until:**
```jinja2
{% set days = state_attr('sensor.bin_collection', 'daysTo') | int %}
{% if days <= 1 %}red
{% elif days <= 3 %}amber
{% elif days <= 7 %}yellow
{% else %}grey
{% endif %}
```

**Conditional Display:**
```jinja2
{% set bins = [] %}
{% if days and days | int <= 7 %}
  {% set bins = bins + ['Recycling'] %}
{% endif %}
{% if bins %}This week: {{ bins | join(', ') }}{% else %}None this week{% endif %}
```

**IMPORTANT:** Always use `| int` or `| float` to avoid type errors when comparing

### Tablet Optimization

**Screen-specific layouts:**
- 11-inch tablets: 3-4 columns
- Touch targets: minimum 44x44px
- Minimize scrolling: Use panel view for full-screen
- Visual feedback: Color-coded status (red/green/amber)

**Grid Layout for Tablets:**
```json
{
  "type": "grid",
  "columns": 3,
  "square": false,
  "cards": [
    {"type": "custom:mushroom-light-card", "entity": "light.living_room"},
    {"type": "custom:mushroom-light-card", "entity": "light.bedroom"}
  ]
}
```

### Common Dashboard Pitfalls

**Problem 1: Dashboard Not in Sidebar**
- **Cause:** File created but not registered
- **Fix:** Add to `.storage/lovelace_dashboards` and restart HA

**Problem 2: "Configuration Error" in Card**
- **Cause:** Custom card not installed, wrong syntax, template error
- **Fix:**
  - Check HACS for card installation
  - Check browser console (F12) for details
  - Test templates in Developer Tools → Template

**Problem 3: Auto-Entities Fails**
- **Cause:** `card_param` not supported by card type
- **Fix:** Use cards that accept `entities` parameter:
  - ✅ Works: `entities`, `vertical-stack`, `horizontal-stack`
  - ❌ Doesn't work: `grid`, `glance` (without specific syntax)

**Problem 4: Vacuum Map Has Margins/Scrolling**
- **Cause:** Using sections view (has margins)
- **Fix:** Use panel view for full-width, no scrolling

**Problem 5: Template Type Errors**
- **Error:** `TypeError: '<' not supported between instances of 'str' and 'int'`
- **Fix:** Use type filters: `states('sensor.days') | int < 7`

### Dashboard Debugging

**1. Browser Console (F12):**
- Check for red errors when loading dashboard
- Common: "Custom element doesn't exist" → Card not installed

**2. Validate JSON Syntax:**
```bash
python3 -m json.tool .storage/lovelace.control_center > /dev/null
```

**3. Test Templates:**
```
Home Assistant → Developer Tools → Template
Paste template to test before adding to dashboard
```

**4. Verify Entities:**
```bash
hass-cli state get binary_sensor.front_door
```

**5. Clear Browser Cache:**
- Hard refresh: Ctrl+F5 or Cmd+Shift+R
- Try incognito window

## Real-World Examples

### Quick Controls Dashboard Section
```json
{
  "type": "grid",
  "title": "Quick Controls",
  "cards": [
    {
      "type": "custom:mushroom-template-card",
      "primary": "All Doors",
      "secondary": "{% set doors = ['binary_sensor.front_door', 'binary_sensor.back_door'] %}\n{% set open = doors | select('is_state', 'on') | list | length %}\n{{ open }} / {{ doors | length }} open",
      "icon": "mdi:door",
      "icon_color": "{% if open > 0 %}red{% else %}green{% endif %}"
    },
    {
      "type": "tile",
      "entity": "climate.thermostat",
      "features": [
        {"type": "climate-hvac-modes", "hvac_modes": ["heat", "cool", "fan_only", "off"]},
        {"type": "target-temperature"}
      ]
    }
  ]
}
```

### Individual Light Cards (Touch-Friendly)
```json
{
  "type": "grid",
  "title": "Lights",
  "columns": 3,
  "cards": [
    {
      "type": "custom:mushroom-light-card",
      "entity": "light.office_studio",
      "name": "Office",
      "use_light_color": true,
      "show_brightness_control": true,
      "collapsible_controls": true
    }
  ]
}
```

### Full-Screen Vacuum Map
```json
{
  "type": "panel",
  "title": "Vacuum",
  "path": "vacuum-map",
  "cards": [
    {
      "type": "custom:xiaomi-vacuum-map-card",
      "vacuum_platform": "Tasshack/dreame-vacuum",
      "entity": "vacuum.dusty"
    }
  ]
}
```

## Common Commands Quick Reference

```bash
# Configuration
ssh jflavigne@homeassistant.local "ha core check"
ssh jflavigne@homeassistant.local "ha core restart"

# Logs
ssh jflavigne@homeassistant.local "ha core logs | tail -50"
ssh jflavigne@homeassistant.local "ha core logs | grep -i error | tail -20"

# State/Services
hass-cli state list
hass-cli state get entity.name
hass-cli service call automation.reload
hass-cli service call automation.trigger --arguments entity_id=automation.name

# Deployment
git add . && git commit -m "..." && git push
ssh jflavigne@homeassistant.local "cd /homeassistant && git pull"
scp file.yaml jflavigne@homeassistant.local:/homeassistant/

# Dashboard deployment
scp .storage/lovelace.my_dashboard jflavigne@homeassistant.local:/homeassistant/.storage/
python3 -m json.tool .storage/lovelace.my_dashboard > /dev/null  # Validate JSON

# Quick test cycle
scp automations.yaml jflavigne@homeassistant.local:/homeassistant/
hass-cli service call automation.reload
hass-cli service call automation.trigger --arguments entity_id=automation.name
ssh jflavigne@homeassistant.local "ha core logs | grep -i 'automation' | tail -10"
```

## Best Practices Summary

1. **Always check configuration** before restart: `ha core check`
2. **Prefer reload over restart** when possible
3. **Test automations manually** after deployment
4. **Check logs** for errors after every change
5. **Use scp for rapid iteration**, git for final changes
6. **Verify outcomes** - don't assume it worked
7. **Use Context7** for current documentation
8. **Test templates in Dev Tools** before adding to dashboards
9. **Validate JSON syntax** before deploying dashboards
10. **Test on actual device** for tablet dashboards
11. **Color-code status** for visual feedback (red/green/amber)
12. **Commit only stable versions** - test with scp first

## Workflow Decision Tree

```
Configuration Change Needed
├─ Is this final/tested?
│  ├─ YES → Use git workflow
│  └─ NO → Use scp workflow
├─ Check configuration valid
├─ Deploy (git pull or scp)
├─ Needs restart?
│  ├─ YES → ha core restart
│  └─ NO → Use appropriate reload
├─ Verify in logs
└─ Test outcome

Dashboard Change Needed
├─ Make changes locally
├─ Deploy via scp for testing
├─ Refresh browser (Ctrl+F5)
├─ Test on target device
├─ Iterate until perfect
└─ Commit to git when stable
```

## Entity Registry Management

### Understanding Automation IDs vs Entity IDs

**Critical distinction:**
- **YAML `id` field** → becomes `unique_id` in entity registry (internal identifier)
- **YAML `alias` field** → becomes `entity_id` (e.g., `automation.kitchen_thermostat_schedule`)

**WARNING: Changing automation IDs causes problems!**
When you change an automation's `id` field:
1. HA sees it as a completely NEW automation
2. Creates a new entity registry entry
3. Since the `alias` generates the same `entity_id`, HA adds `_2` suffix
4. Old metadata (area, icon, labels) is orphaned on the old entry

### Labels, Icons, and Areas are UI-Only

**These CANNOT be set via YAML:**
- Labels
- Icons (for automations)
- Area assignments

**They are stored in:** `.storage/core.entity_registry`

**To set them:**
1. Via HA UI: Settings → Automations → Select → 3-dot menu → Edit metadata
2. Via WebSocket API (undocumented): `config/entity_registry/update`

**The MCP server does NOT support setting labels/icons** - it only provides device control.

### Fixing Duplicate `_2` Automation Entries

If you changed automation IDs and have duplicates:

**The Fix Process:**
```bash
# 1. Stop HA (NOT restart - must stop completely)
curl -X POST "http://homeassistant.local:8123/api/services/homeassistant/stop" \
  -H "Authorization: Bearer $HASS_TOKEN"

# 2. Wait for HA to stop
sleep 15

# 3. Run fix script (updates unique_ids, removes duplicates)
# See /tmp/ha_fix_registry_final.py or create similar

# 4. Reboot system (since we can't start HA via SSH add-on)
ssh jflavigne@homeassistant.local "sudo reboot"
```

**Fix Script Logic:**
```python
# For each _2 entry:
#   1. Find matching non-_2 entry (has metadata)
#   2. Update non-_2 entry's unique_id to match new YAML id
#   3. Delete the _2 entry
# Result: Clean entity_ids with preserved metadata
```

**Key insight:** Registry changes must be made while HA is STOPPED. HA overwrites registry from memory on shutdown.

### Entity Registry Structure

```json
{
  "entity_id": "automation.kitchen_thermostat_schedule",
  "unique_id": "climate_kitchen_thermostat_schedule",  // <-- matches YAML id
  "area_id": "kitchen",
  "icon": "mdi:home-thermometer-outline",
  "labels": ["thermostat"],
  "platform": "automation"
}
```

### Best Practices for Automation IDs

1. **Pick descriptive IDs from the start** - avoid changing them later
2. **Use consistent naming convention:** `domain_room_action` (e.g., `climate_kitchen_thermostat_schedule`)
3. **If you must change IDs:** Be prepared to run the registry fix process
4. **Document your ID scheme** to maintain consistency

## Automation Metadata Tools

Scripts in `scripts/` directory for managing automation labels, icons, and areas programmatically.

### Prerequisites

```bash
pip install websockets pyyaml
```

### Tool 1: Registry Backup (`ha_backup_registry.py`)

Create timestamped backups of the entity registry before making changes.

```bash
# Create backup
python3 scripts/ha_backup_registry.py backup

# List existing backups
python3 scripts/ha_backup_registry.py list

# Restore from backup (requires HA stopped)
python3 scripts/ha_backup_registry.py restore 20260107_120000

# Clean old backups (keep last 5)
python3 scripts/ha_backup_registry.py clean --keep 5
```

Backups stored in: `scripts/backups/entity_registry.<timestamp>.json`

### Tool 2: Entity Metadata (`ha_entity_metadata.py`)

Bulk assign labels, icons, and areas via WebSocket API.

```bash
# ALWAYS START WITH STATS - shows what's missing
python3 scripts/ha_entity_metadata.py stats

# Export ALL automations (including those without metadata)
python3 scripts/ha_entity_metadata.py export --all > all_automations.yaml

# Export only automations that already have metadata
python3 scripts/ha_entity_metadata.py export > metadata.yaml

# Apply metadata from config file
python3 scripts/ha_entity_metadata.py apply metadata.yaml

# Preview changes without applying
python3 scripts/ha_entity_metadata.py apply metadata.yaml --dry-run

# Set single automation
python3 scripts/ha_entity_metadata.py set automation.kitchen_thermostat \
    --icon mdi:thermometer --area kitchen --labels thermostat,climate

# Label management
python3 scripts/ha_entity_metadata.py labels list
python3 scripts/ha_entity_metadata.py labels create climate --icon mdi:thermometer --color blue
python3 scripts/ha_entity_metadata.py labels delete climate
python3 scripts/ha_entity_metadata.py labels suggest climate --pattern "automation.*thermostat*"
```

**IMPORTANT:** Always run `stats` first to see total automation count and coverage!

**Config file format (`automation_metadata.yaml`):**
```yaml
automations:
  automation.kitchen_thermostat_schedule:
    icon: mdi:home-thermometer-outline
    area_id: kitchen
    labels:
      - climate
      - scheduled
```

**Important:** Labels must exist before assignment. Create them first or use the Claude-assisted workflow.

### Tool 3: ID Migration (`ha_migrate_automation_ids.py`)

Safely migrate automation IDs while preserving metadata.

```bash
# Generate migration plan from current state
python3 scripts/ha_migrate_automation_ids.py generate > migration.yaml

# Preview what will change
python3 scripts/ha_migrate_automation_ids.py preview migration.yaml

# Execute full migration (stops HA, updates registry, reboots)
python3 scripts/ha_migrate_automation_ids.py execute migration.yaml

# Fix registry after YAML already updated (removes _2 duplicates)
python3 scripts/ha_migrate_automation_ids.py fix-registry
```

**Migration workflow:**
1. Update YAML `id` fields with new descriptive IDs
2. Generate or edit migration.yaml
3. Run `execute` - tool handles stop/migrate/reboot

### Label Management Workflow (Claude-Assisted)

Labels require thoughtful planning. Use this workflow:

1. **Check current coverage (CRITICAL FIRST STEP):**
   ```bash
   python3 scripts/ha_entity_metadata.py stats
   ```

2. **List existing labels:**
   ```bash
   python3 scripts/ha_entity_metadata.py labels list
   ```

3. **Export ALL automations for analysis:**
   ```bash
   python3 scripts/ha_entity_metadata.py export --all > all_automations.yaml
   ```

4. **Plan label taxonomy** (Claude can help analyze automations and suggest labels)

5. **Create labels:**
   ```bash
   python3 scripts/ha_entity_metadata.py labels create climate --icon mdi:thermometer
   python3 scripts/ha_entity_metadata.py labels create scheduled --icon mdi:clock
   ```

6. **Apply labels to automations:**
   ```bash
   python3 scripts/ha_entity_metadata.py apply metadata.yaml
   ```

7. **Verify coverage:**
   ```bash
   python3 scripts/ha_entity_metadata.py stats
   ```

**Suggested label taxonomy:**

| Label         | Icon                | Purpose                     |
|---------------|---------------------|-----------------------------|
| climate       | mdi:thermometer     | Heating/cooling automations |
| lighting      | mdi:lightbulb       | Light control automations   |
| vacuum        | mdi:robot-vacuum    | Robot vacuum automations    |
| media         | mdi:television      | Media player automations    |
| notifications | mdi:bell            | Alert automations           |
| scheduled     | mdi:clock           | Time-triggered automations  |
| presence      | mdi:account         | Occupancy-based automations |
| safety        | mdi:shield          | Critical/safety automations |

### Common Mistakes to Avoid

1. **Not running `stats` first** - The `export` command without `--all` only shows automations that ALREADY have metadata. Always run `stats` to see the true count.

2. **Assuming export shows everything** - Use `export --all` to see ALL automations including those without any metadata assigned.

3. **Not verifying after bulk updates** - Always run `stats` after applying changes to confirm coverage.

4. **Forgetting labels must exist first** - Labels must be created before they can be assigned to automations.

5. **Changes are immediate via WebSocket** - No git push or HA restart needed. Changes apply instantly to HA's entity registry. Just refresh browser to see them.

---

This skill encapsulates efficient Home Assistant management workflows developed through iterative optimization and real-world dashboard development. Apply these patterns to any Home Assistant instance for reliable, fast, and safe configuration management.
