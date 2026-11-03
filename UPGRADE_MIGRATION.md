# Upgrade and Migration: v6 → v7

1. Back up the existing `/uneXpected/` Library and local state. Do not overwrite or move legacy/core files.
2. Keep v6 workflow cards/catalog as read-only sources. The generated `MIGRATION_CROSSWALK_V6_TO_V7.*` maps all 120 v6 cards to canonical roles.
3. Keep the 37 legacy profile files unchanged. `EXISTING_37_CROSSWALK.md` maps each to its v7 spec and records `kept`.
4. Extract v7 into a separate folder. Compare the manifest and run tests before changing any Project settings.
5. Migrate durable facts into agent-specific namespaces only after provenance/privacy review; do not blindly import secrets or raw untrusted instructions.
6. If adopting a real provider or connector, configure it separately and run authorization/permission tests. No external tools are migrated automatically.
7. Switch the active Project instructions only after manual review. Preserve v6 and legacy ZIPs until rollback is no longer needed.
