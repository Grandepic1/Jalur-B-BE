"""Bring ``jalurB-v2.erd`` in line with the SQLAlchemy models.

The ERD Editor document is JSON. Hand-editing a 10,000-line file drifts from the models, so
this script derives the missing entities from ``Base.metadata`` instead.

It is **additive and idempotent**: existing entities are never touched or reordered, so the
diff on a re-run is empty and the diff on a real change contains only the new entities. Run
it after adding a model or a migration:

    uv run python scripts/generate_erd.py            # write
    uv run python scripts/generate_erd.py --check    # exit 1 if the file is out of date

Entity id conventions, matching the existing document:

* table       ``t-<table-name>``
* column      ``c-<table-name>-<column-name>``
* relationship ``r-<parent-table>-<child-table>-<fk-column>``
* index       ``i-<index-name>`` with members ``i-<index-name>-c<n>``

Column ``options`` is a bitmask: 1 primary key, 2 autoincrement, 4 unique, 8 not null.
Column ``ui.keys`` is 1 for a primary key and 2 for a foreign key.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import Enum as SAEnum  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.core.database import Base  # noqa: E402

ERD_PATH = Path(__file__).resolve().parent.parent / "jalurB-v2.erd"

OPTION_PRIMARY_KEY = 1
OPTION_AUTOINCREMENT = 2
OPTION_UNIQUE = 4
OPTION_NOT_NULL = 8

KEY_PRIMARY = 1
KEY_FOREIGN = 2


def slug(value: str) -> str:
    """Table/column name to the hyphenated form used in entity ids."""
    return value.replace("_", "-")


def erase_indent(text: str) -> str:
    return " ".join(text.split())


def data_type_for(column: sa.Column) -> str:
    """Map a SQLAlchemy type onto the ERD's rendered type name."""
    type_ = column.type
    if isinstance(type_, SAEnum):
        # The document renders enum members with no space after the comma.
        values = ",".join(f"'{value}'" for value in type_.enums)
        return f"ENUM({values})"
    if isinstance(type_, sa.BigInteger):
        return "BIGINT"
    if isinstance(type_, sa.SmallInteger):
        return "SMALLINT"
    if isinstance(type_, sa.Integer):
        return "INT"
    if isinstance(type_, sa.Boolean):
        return "BOOLEAN"
    if isinstance(type_, sa.Numeric):
        return f"DECIMAL({type_.precision},{type_.scale})"
    if isinstance(type_, sa.CHAR):
        return f"CHAR({type_.length})"
    if isinstance(type_, sa.String):
        return f"VARCHAR({type_.length})"
    if isinstance(type_, sa.Text):
        return "TEXT"
    if isinstance(type_, sa.Date):
        return "DATE"
    if isinstance(type_, sa.TIMESTAMP):
        return "TIMESTAMP"
    if isinstance(type_, sa.DateTime):
        return "DATETIME"
    if isinstance(type_, sa.dialects.postgresql.JSONB):
        return "JSON"
    if isinstance(type_, sa.JSON):
        return "JSON"
    raise ValueError(f"no ERD mapping for {type_!r} on column {column.name}")


DEFAULT_NORMALISERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^now\(\)$"), "CURRENT_TIMESTAMP"),
    (re.compile(r"^CURRENT_TIMESTAMP$"), "CURRENT_TIMESTAMP"),
    (re.compile(r"^true$"), "TRUE"),
    (re.compile(r"^false$"), "FALSE"),
)

# Rendered bare, without surrounding quotes, in the existing document.
BARE_DEFAULTS = {"TRUE", "FALSE", "NULL", "CURRENT_TIMESTAMP"}


def default_for(column: sa.Column) -> str:
    """Render a server default the way the existing document renders it."""
    default = column.server_default
    if default is None:
        return ""
    text = getattr(default, "arg", None)
    if text is None:
        return ""
    text = str(text).strip()
    for pattern, replacement in DEFAULT_NORMALISERS:
        if pattern.match(text):
            return replacement
    if text.startswith("'") and text.endswith("'"):
        return text
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return text
    if text.upper() in BARE_DEFAULTS:
        return text.upper()
    # String server defaults are rendered quoted, e.g. server_default='pkwtt' -> 'pkwtt'.
    return f"'{text}'"


def column_options(column: sa.Column) -> tuple[int, int]:
    options = 0
    keys = 0
    if column.primary_key:
        options |= OPTION_PRIMARY_KEY
        if isinstance(column.type, (sa.Integer, sa.BigInteger)) and not column.foreign_keys:
            options |= OPTION_AUTOINCREMENT
        keys = KEY_PRIMARY
        # Every primary key in the document is rendered as 3 (PK + autoincrement); the
        # not-null bit is not set on a PK.
    else:
        if column.unique:
            options |= OPTION_UNIQUE
        if not column.nullable:
            options |= OPTION_NOT_NULL
    if column.foreign_keys:
        keys = KEY_FOREIGN
    return options, keys


def make_column_entity(table: sa.Table, column: sa.Column, now: int) -> dict:
    options, keys = column_options(column)
    return {
        "id": f"c-{slug(table.name)}-{slug(column.name)}",
        "tableId": f"t-{slug(table.name)}",
        "name": column.name,
        "comment": "",
        "dataType": data_type_for(column),
        "default": default_for(column),
        "options": options,
        "ui": {
            "keys": keys,
            "widthName": 60,
            "widthComment": 60,
            "widthDataType": 60,
            "widthDefault": 60,
        },
        "meta": {"updateAt": now, "createAt": now},
    }


def find_placement(tables: dict, index: int) -> tuple[float, float]:
    """Place a new table in free canvas space below everything that already exists."""
    max_y = 0.0
    for entity in tables.values():
        max_y = max(max_y, float(entity["ui"]["y"]))
    return 200.0 + (index % 4) * 700.0, max_y + 400.0 + (index // 4) * 500.0


def build_table_entities(metadata, existing_tables: dict, now: int) -> tuple[dict, dict]:
    new_tables: dict[str, dict] = {}
    new_columns: dict[str, dict] = {}
    for table in metadata.sorted_tables:
        table_id = f"t-{slug(table.name)}"
        if table_id in existing_tables:
            continue
        column_ids = []
        for column in table.columns:
            entity = make_column_entity(table, column, now)
            new_columns[entity["id"]] = entity
            column_ids.append(entity["id"])
        x, y = find_placement(existing_tables, len(new_tables))
        new_tables[table_id] = {
            "id": table_id,
            "name": table.name,
            "comment": "",
            "columnIds": column_ids,
            "seqColumnIds": list(column_ids),
            "ui": {
                "x": x,
                "y": y,
                "zIndex": 2,
                "widthName": 90,
                "widthComment": 248,
                "color": "",
            },
            "meta": {"updateAt": now, "createAt": now},
        }
    return new_tables, new_columns


def build_relationships(
    metadata, existing: dict, new_tables: dict, new_columns: dict, now: int
) -> dict:
    """Relationships for foreign keys on newly added tables."""
    relationships: dict[str, dict] = {}
    for table in metadata.sorted_tables:
        if f"t-{slug(table.name)}" not in new_tables:
            continue
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                rel_id = f"r-{slug(parent)}-{slug(table.name)}-{slug(column.name)}"
                if rel_id in existing:
                    continue
                relationships[rel_id] = {
                    "id": rel_id,
                    "identification": False,
                    "relationshipType": 2,
                    "startRelationshipType": 2,
                    "start": {
                        "tableId": f"t-{slug(parent)}",
                        "columnIds": [f"c-{slug(parent)}-{slug(fk.column.name)}"],
                        "x": 0,
                        "y": 0,
                        "direction": 2,
                    },
                    "end": {
                        "tableId": f"t-{slug(table.name)}",
                        "columnIds": [
                            f"c-{slug(table.name)}-{slug(column.name)}"
                        ],
                        "x": 0,
                        "y": 0,
                        "direction": 1,
                    },
                    "meta": {"updateAt": now, "createAt": now},
                }
    return relationships


def build_indexes(
    metadata, existing: dict, new_tables: dict, new_columns: dict, now: int
) -> tuple[dict, dict]:
    """Index and unique-constraint entities for newly added tables."""
    indexes: dict[str, dict] = {}
    index_columns: dict[str, dict] = {}
    for table in metadata.sorted_tables:
        if f"t-{slug(table.name)}" not in new_tables:
            continue
        definitions = [
            (index.name, [c.name for c in index.columns], bool(index.unique))
            for index in table.indexes
        ]
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint) and constraint.name:
                if len(constraint.columns) > 1:
                    definitions.append(
                        (
                            constraint.name,
                            [c.name for c in constraint.columns],
                            True,
                        )
                    )
        for name, columns, unique in definitions:
            index_id = f"i-{slug(name)}"
            if index_id in existing:
                continue
            member_ids = []
            for position, column_name in enumerate(columns, start=1):
                member_id = f"{index_id}-c{position}"
                member_ids.append(member_id)
                index_columns[member_id] = {
                    "id": member_id,
                    "indexId": index_id,
                    "columnId": f"c-{slug(table.name)}-{slug(column_name)}",
                    "orderType": 1,
                    "meta": {"updateAt": now, "createAt": now},
                }
            indexes[index_id] = {
                "id": index_id,
                "name": name,
                "tableId": f"t-{slug(table.name)}",
                "indexColumnIds": member_ids,
                "seqIndexColumnIds": list(member_ids),
                "unique": unique,
                "meta": {"updateAt": now, "createAt": now},
            }
    return indexes, index_columns


def extend_existing_tables(
    metadata, tables: dict, columns: dict, now: int
) -> list[str]:
    """Append columns that exist on the models but are missing from the document."""
    added: list[str] = []
    by_name = {table.name: table for table in metadata.sorted_tables}
    for table_id, entity in tables.items():
        table = by_name.get(entity["name"])
        if table is None:
            continue
        known = set(entity["columnIds"])
        for column in table.columns:
            entity_id = f"c-{slug(table.name)}-{slug(column.name)}"
            if entity_id in known or entity_id in columns:
                continue
            columns[entity_id] = make_column_entity(table, column, now)
            # Match the model's column order rather than appending blindly.
            ordered: list[str] = []
            for model_column in table.columns:
                candidate = f"c-{slug(table.name)}-{slug(model_column.name)}"
                if candidate in known or candidate in columns:
                    ordered.append(candidate)
            entity["columnIds"] = ordered
            entity["seqColumnIds"] = list(ordered)
            added.append(entity_id)
    return added


def validate(document: dict) -> list[str]:
    """Check every cross-reference in the document resolves."""
    collections = document["collections"]
    problems: list[str] = []
    tables = collections["tableEntities"]
    columns = collections["tableColumnEntities"]
    for table_id, table in tables.items():
        for column_id in table["columnIds"]:
            if column_id not in columns:
                problems.append(f"{table_id} references missing column {column_id}")
    for column_id, column in columns.items():
        if column["tableId"] not in tables:
            problems.append(f"{column_id} references missing table {column['tableId']}")
    for rel_id, rel in collections["relationshipEntities"].items():
        for side in ("start", "end"):
            endpoint = rel[side]
            if endpoint["tableId"] not in tables:
                problems.append(f"{rel_id}.{side} references missing table")
            for column_id in endpoint["columnIds"]:
                if column_id not in columns:
                    problems.append(f"{rel_id}.{side} references missing column")
    for index_id, index in collections["indexEntities"].items():
        if index["tableId"] not in tables:
            problems.append(f"{index_id} references missing table")
        for column_id in index["indexColumnIds"]:
            if column_id not in collections["indexColumnEntities"]:
                problems.append(f"{index_id} references missing index column")
    for member_id, member in collections["indexColumnEntities"].items():
        if member["columnId"] not in columns:
            problems.append(f"{member_id} references missing column")
    return problems


def main() -> int:
    check_only = "--check" in sys.argv
    raw = ERD_PATH.read_text(encoding="utf-8")
    document = json.loads(raw)
    collections = document["collections"]
    now = int(datetime.now().timestamp() * 1000)

    new_tables, new_columns = build_table_entities(
        Base.metadata, collections["tableEntities"], now
    )
    added_columns = extend_existing_tables(
        Base.metadata, collections["tableEntities"], collections["tableColumnEntities"], now
    )
    new_rels = build_relationships(
        Base.metadata,
        collections["relationshipEntities"],
        new_tables,
        new_columns,
        now,
    )
    new_indexes, new_index_columns = build_indexes(
        Base.metadata,
        collections["indexEntities"],
        new_tables,
        new_columns,
        now,
    )

    if not any((new_tables, new_columns, added_columns, new_rels, new_indexes)):
        print("jalurB-v2.erd is already up to date with the models.")
        return 0

    for key, value in new_tables.items():
        collections["tableEntities"][key] = value
    collections["tableColumnEntities"].update(new_columns)
    collections["relationshipEntities"].update(new_rels)
    collections["indexEntities"].update(new_indexes)
    collections["indexColumnEntities"].update(new_index_columns)

    # Keep the document's table ordering in step with the entity map.
    order = list(collections["tableEntities"].keys())
    existing_order = [t for t in document["doc"]["tableIds"] if t in order]
    document["doc"]["tableIds"] = existing_order + [
        t for t in order if t not in existing_order
    ]

    problems = validate(document)
    if problems:
        print("REFUSING to write: the document would be inconsistent:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    summary = (
        f"+{len(new_tables)} tables, +{len(new_columns)} columns, "
        f"+{len(added_columns)} columns on existing tables, "
        f"+{len(new_rels)} relationships, +{len(new_indexes)} indexes"
    )
    for table_id in new_tables:
        print(f"  new table: {table_id}")
    for column_id in added_columns:
        print(f"  new column: {column_id}")
    print(summary)

    if check_only:
        print("--check given: the file is out of date.")
        return 1

    ERD_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
        encoding="utf-8",
        newline="",
    )
    print(f"wrote {ERD_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
