"""
Safe accessors for Notion API property payloads.

Notion API shapes by type:
  rich_text / title: {"rich_text": [...]} or {"title": [...]} — array, may be empty
  select:            {"select": {"name": "..."}} or {"select": null}
  checkbox:          {"checkbox": true/false}
"""


def get_property(properties: dict, property_id: str | None) -> dict:
    """Resolve a page property by stable provider ID, not its mutable name."""
    if not property_id:
        return {}
    for value in properties.values():
        if isinstance(value, dict) and value.get("id") == property_id:
            return value
    return {}


def get_rich_text(properties: dict, property_id: str | None) -> str | None:
    items = get_property(properties, property_id).get("rich_text", [])
    return items[0].get("plain_text") if items else None


def get_title(properties: dict, property_id: str | None) -> str | None:
    items = get_property(properties, property_id).get("title", [])
    return items[0].get("plain_text") if items else None


def get_select(properties: dict, property_id: str | None) -> str | None:
    select = get_property(properties, property_id).get("select") or {}
    return select.get("name")


def get_checkbox(properties: dict, property_id: str | None) -> bool:
    return get_property(properties, property_id).get("checkbox", False)
