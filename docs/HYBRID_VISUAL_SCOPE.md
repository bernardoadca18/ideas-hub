# Hybrid visual media scope

`ScriptMediaContext` may opt a production script into first-class static-image retrieval with
`static_images.enabled=true`. The scope can narrow eligible indexed images through
`asset_classes`, `collections`, `source_owners`, and `source_classes`. Values are trimmed,
bounded, unique strings; invalid or duplicate filters are rejected.

The field is optional. Its absence preserves the historical video-only contract and script
content identity. Enabling it is metadata-only: Ideas Hub never selects a concrete asset or a
visual source type, and existing `VisualQuery` IDs and claims/evidence remain unchanged.

The provenance fields are orthogonal. `asset_class` classifies the asset, `collection` identifies
an operator-managed grouping or source pack, and `game` is a separate Media Indexer provenance
field. A collection must not be populated with a game name. The current scope intentionally
exposes only the filters needed by production; project ownership already fixes the broader media
domain.

Example:

```json
{
  "media_project_id": "00000000-0000-4000-8000-000000000001",
  "media_session_ids": null,
  "static_images": {
    "enabled": true,
    "asset_classes": ["official_screenshot", "official_artwork"],
    "collections": ["screenshots", "artwork_wallpapers"],
    "source_owners": ["rockstar_games"],
    "source_classes": ["official"]
  }
}
```
