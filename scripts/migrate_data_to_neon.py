"""Migrate data from JSON files to Neon PostgreSQL database."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_access.json_loader import JsonDataStore
from app.data_access.schema import DATASETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

# Table migration order (respects foreign key dependencies)
MIGRATION_ORDER = [
    "customers",    # No dependencies
    "products",     # No dependencies
    "employees",    # Self-referencing, but nullable manager_id
    "orders",       # Depends on customers
    "order_items",  # Depends on orders and products
]
MIGRATION_BATCH_SIZE = 100
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _quote_identifier(identifier: str) -> str:
    """Quote a validated SQL identifier used in migration statements."""
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _table_metadata(
    cursor: psycopg2.extensions.cursor,
    table_name: str,
) -> tuple[list[str], list[str]]:
    """Read the real target table columns and primary-key columns."""
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    columns = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        """
        SELECT key_column.column_name
        FROM information_schema.table_constraints AS table_constraint
        JOIN information_schema.key_column_usage AS key_column
          ON key_column.constraint_catalog = table_constraint.constraint_catalog
         AND key_column.constraint_schema = table_constraint.constraint_schema
         AND key_column.constraint_name = table_constraint.constraint_name
         AND key_column.table_schema = table_constraint.table_schema
         AND key_column.table_name = table_constraint.table_name
        WHERE table_constraint.constraint_type = 'PRIMARY KEY'
          AND table_constraint.table_schema = 'public'
          AND table_constraint.table_name = %s
        ORDER BY key_column.ordinal_position
        """,
        (table_name,),
    )
    primary_key = [row[0] for row in cursor.fetchall()]
    if not columns or not primary_key:
        raise ValueError(
            f"Table '{table_name}' is missing or has no primary key."
        )
    return columns, primary_key


def _validate_records(
    table_name: str,
    records: list[dict],
    table_columns: list[str],
    primary_key: list[str],
) -> list[str]:
    """Ensure source rows match the approved schema and target key."""
    approved_columns = set(DATASETS[table_name].fields)
    if not records:
        return list(DATASETS[table_name].fields)
    columns = list(records[0])
    if set(columns) != approved_columns:
        raise ValueError(
            f"{table_name}.json fields do not match the approved schema: "
            f"expected {sorted(approved_columns)}, found {sorted(columns)}."
        )
    missing_columns = set(columns) - set(table_columns)
    missing_key = set(primary_key) - set(columns)
    if missing_columns or missing_key:
        raise ValueError(
            f"Target table '{table_name}' is incompatible with its JSON source; "
            f"missing columns={sorted(missing_columns)}, "
            f"missing primary-key fields={sorted(missing_key)}."
        )

    seen_keys: set[tuple[object, ...]] = set()
    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != set(columns):
            raise ValueError(
                f"{table_name}.json row {row_number} has inconsistent fields."
            )
        key = tuple(record[column] for column in primary_key)
        if key in seen_keys:
            raise ValueError(
                f"{table_name}.json contains duplicate primary key {key!r}."
            )
        seen_keys.add(key)
    return columns


def _build_upsert_query(
    table_name: str,
    columns: list[str],
    primary_key: list[str],
) -> str:
    """Build an insert that adds new rows and refreshes changed source rows."""
    quoted_table = _quote_identifier(table_name)
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    conflict_columns = ", ".join(
        _quote_identifier(column) for column in primary_key
    )
    update_columns = [column for column in columns if column not in primary_key]
    if update_columns:
        conflict_action = "DO UPDATE SET " + ", ".join(
            f"{_quote_identifier(column)} = "
            f"EXCLUDED.{_quote_identifier(column)}"
            for column in update_columns
        )
    else:
        conflict_action = "DO NOTHING"
    return (
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES %s "
        f"ON CONFLICT ({conflict_columns}) {conflict_action}"
    )


def load_json_data(data_dir: Path, dataset_name: str) -> list[dict]:
    """Load a JSON dataset from the data directory."""
    file_path = data_dir / f"{dataset_name}.json"
    
    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError(f"{dataset_name}.json must contain a JSON array")
        
        LOGGER.info(f"Loaded {len(data)} records from {dataset_name}.json")
        return data
    
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {file_path}: {exc}") from exc


def migrate_table(
    cursor: psycopg2.extensions.cursor,
    table_name: str,
    records: list[dict],
) -> int:
    """Insert new rows and update existing rows from the JSON source."""
    if not records:
        LOGGER.warning("No records to migrate for %s", table_name)
        return 0
    table_columns, primary_key = _table_metadata(cursor, table_name)
    columns = _validate_records(
        table_name,
        records,
        table_columns,
        primary_key,
    )
    insert_query = _build_upsert_query(table_name, columns, primary_key)
    values = [tuple(record[column] for column in columns) for record in records]

    try:
        affected = 0
        for offset in range(0, len(values), MIGRATION_BATCH_SIZE):
            batch = values[offset : offset + MIGRATION_BATCH_SIZE]
            execute_values(
                cursor,
                insert_query,
                batch,
                page_size=MIGRATION_BATCH_SIZE,
            )
            affected += cursor.rowcount
        LOGGER.info(
            "✓ Inserted or updated %d source records in %s",
            affected,
            table_name,
        )
        return affected
    except psycopg2.Error as exc:
        LOGGER.error("Failed to upsert %s: %s", table_name, exc)
        raise


def verify_migration(
    cursor: psycopg2.extensions.cursor,
    table_name: str,
    records: list[dict],
) -> bool:
    """Verify all JSON source keys exist, allowing unrelated target rows."""
    table_columns, primary_key = _table_metadata(cursor, table_name)
    _validate_records(table_name, records, table_columns, primary_key)
    cursor.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
    )
    target_count = cursor.fetchone()[0]
    if not records:
        matched_count = 0
    else:
        key_columns = ", ".join(
            _quote_identifier(column) for column in primary_key
        )
        join_condition = " AND ".join(
            f"target.{_quote_identifier(column)} = "
            f"source.{_quote_identifier(column)}"
            for column in primary_key
        )
        query = (
            f"SELECT COUNT(*) FROM {_quote_identifier(table_name)} AS target "
            f"JOIN (VALUES %s) AS source ({key_columns}) ON {join_condition}"
        )
        keys = [
            tuple(record[column] for column in primary_key)
            for record in records
        ]
        matched_count = 0
        for offset in range(0, len(keys), MIGRATION_BATCH_SIZE):
            batch = keys[offset : offset + MIGRATION_BATCH_SIZE]
            result = execute_values(
                cursor,
                query,
                batch,
                page_size=MIGRATION_BATCH_SIZE,
                fetch=True,
            )
            matched_count += result[0][0]

    if matched_count == len(records):
        LOGGER.info(
            "✓ Verification passed for %s: all %d JSON records present "
            "(%d rows total in database)",
            table_name,
            matched_count,
            target_count,
        )
        return True
    LOGGER.error(
        "✗ Verification failed for %s: %d of %d source keys found "
        "(%d rows total in database)",
        table_name,
        matched_count,
        len(records),
        target_count,
    )
    return False


def migrate_all_data(database_url: str, data_dir: Path) -> None:
    """Migrate all datasets from JSON to PostgreSQL."""
    LOGGER.info("Starting data migration to Neon PostgreSQL...")
    if set(MIGRATION_ORDER) != set(DATASETS):
        raise ValueError(
            "Migration order does not match the approved business datasets."
        )
    source_store = JsonDataStore(data_dir)
    if set(source_store.dataset_names) != set(MIGRATION_ORDER):
        raise ValueError(
            "The JSON data store datasets do not match the migration order."
        )
    
    connection = None
    try:
        # Connect to database
        connection = psycopg2.connect(database_url)
        cursor = connection.cursor()
        
        LOGGER.info("Connected to database successfully")
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        missing_tables = set(MIGRATION_ORDER) - existing_tables
        if missing_tables:
            raise ValueError(
                f"Missing tables in database: {sorted(missing_tables)}. "
                "Run scripts/create_neon_schema.py first."
            )
        
        LOGGER.info("All required tables exist")
        
        # Migrate each table in dependency order
        migration_stats = {}
        
        for table_name in MIGRATION_ORDER:
            LOGGER.info(f"\n{'='*60}")
            LOGGER.info(f"Migrating {table_name}...")
            LOGGER.info(f"{'='*60}")
            
            # Load JSON data
            records = load_json_data(data_dir, table_name)
            
            affected = migrate_table(cursor, table_name, records)
            verified = verify_migration(cursor, table_name, records)
            cursor.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
            )
            target_count = cursor.fetchone()[0]
            if verified:
                migration_stats[table_name] = {
                    "source_count": len(records),
                    "affected": affected,
                    "target_count": target_count,
                    "status": "success",
                }
            else:
                migration_stats[table_name] = {
                    "source_count": len(records),
                    "affected": affected,
                    "target_count": target_count,
                    "status": "failed",
                }
        
        all_success = all(
            stats["status"] == "success"
            for stats in migration_stats.values()
        )
        if all_success:
            connection.commit()
        else:
            connection.rollback()

        # Print summary
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)
        
        total_affected = 0
        
        for table_name, stats in migration_stats.items():
            status_icon = "✓" if stats["status"] == "success" else "✗"
            print(
                f"{status_icon} {table_name:15} "
                f"{stats['affected']:6} inserted/updated; "
                f"{stats['source_count']:6} source records; "
                f"{stats['target_count']:6} total in Neon"
            )
            total_affected += stats["affected"]
            if stats['status'] != "success":
                all_success = False
        
        print("="*70)
        print(
            "Total source records inserted or updated: "
            f"{total_affected}"
        )
        print("="*70)
        
        if all_success:
            LOGGER.info("\n✓ Data migration completed successfully!")
            LOGGER.info("\nNext steps:")
            LOGGER.info("  1. Update .env: SET USE_DATABASE=true")
            LOGGER.info("  2. Restart your application")
            LOGGER.info("  3. Test with: python -m app.cli 'How many customers do we have?'")
        else:
            raise RuntimeError(
                "Some tables failed verification; the migration was rolled back."
            )
        
        cursor.close()
        
    except FileNotFoundError as exc:
        LOGGER.error(f"File error: {exc}")
        sys.exit(1)
    except ValueError as exc:
        LOGGER.error(f"Validation error: {exc}")
        sys.exit(1)
    except psycopg2.Error as exc:
        LOGGER.error(f"Database error: {exc}")
        if connection:
            connection.rollback()
        sys.exit(1)
    except Exception as exc:
        LOGGER.error(f"Unexpected error: {exc}")
        if connection:
            connection.rollback()
        sys.exit(1)
    finally:
        if connection:
            connection.close()
            LOGGER.info("Database connection closed")


def main() -> None:
    """Load configuration and migrate data."""
    load_dotenv(PROJECT_ROOT / ".env")
    
    database_url = os.getenv("NEON_DATABASE_URL", "").strip()
    data_dir_path = os.getenv("DATA_DIR", "tests/fixtures/business_data")
    
    if not database_url:
        LOGGER.error(
            "NEON_DATABASE_URL is not set in .env file. "
            "Please add your Neon PostgreSQL connection string."
        )
        sys.exit(1)
    
    data_dir = Path(data_dir_path)
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    
    if not data_dir.exists():
        LOGGER.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("DATA MIGRATION TO NEON")
    print("="*70)
    print(f"\nSource: {data_dir}")
    print(f"Target: Neon PostgreSQL")
    print("\nThis will insert new JSON records and update matching records in Neon.")
    print("Records in Neon that are absent from JSON will not be deleted.")
    print("="*70)
    
    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    
    if response not in ("yes", "y"):
        LOGGER.info("Migration cancelled by user")
        sys.exit(0)
    
    try:
        migrate_all_data(database_url, data_dir)
    except Exception as exc:
        LOGGER.error(f"Migration failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
