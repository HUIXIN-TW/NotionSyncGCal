"""
Safe accessors for Notion API property payloads.

Notion API shapes by type:
  rich_text / title: {"rich_text": [...]} or {"title": [...]} — array, may be empty
  select:            {"select": {"name": "..."}} or {"select": null}
  checkbox:          {"checkbox": true/false}
"""


def get_rich_text(properties: dict, column_name: str) -> str | None:
    items = properties.get(column_name, {}).get("rich_text", [])
    return items[0].get("plain_text") if items else None


def get_title(properties: dict, column_name: str) -> str | None:
    items = properties.get(column_name, {}).get("title", [])
    return items[0].get("plain_text") if items else None


def get_select(properties: dict, column_name: str) -> str | None:
    select = (properties.get(column_name) or {}).get("select") or {}
    return select.get("name")


def get_checkbox(properties: dict, column_name: str) -> bool:
    return properties.get(column_name, {}).get("checkbox", False)
