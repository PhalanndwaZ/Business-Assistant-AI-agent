"""Migrate data from JSON files to Neon PostgreSQL database."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_batch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

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
    """Insert records into a database table using batch insert."""
    if not records:
        LOGGER.warning(f"No records to migrate for {table_name}")
        return 0
    
    # Get column names from first record
    columns = list(records[0].keys())
    column_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    
    insert_query = f"""
        INSERT INTO {table_name} ({column_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """
    
    # Convert records to tuples in correct order
    values = [tuple(record[col] for col in columns) for record in records]
    
    try:
        execute_batch(cursor, insert_query, values, page_size=100)
        inserted = cursor.rowcount
        LOGGER.info(f"✓ Inserted {inserted} records into {table_name}")
        return inserted
    
    except psycopg2.Error as exc:
        LOGGER.error(f"Failed to insert into {table_name}: {exc}")
        raise


def verify_migration(
    cursor: psycopg2.extensions.cursor,
    table_name: str,
    expected_count: int,
) -> bool:
    """Verify that all records were migrated successfully."""
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    actual_count = cursor.fetchone()[0]
    
    if actual_count == expected_count:
        LOGGER.info(f"✓ Verification passed for {table_name}: {actual_count} rows")
        return True
    else:
        LOGGER.error(
            f"✗ Verification failed for {table_name}: "
            f"expected {expected_count}, found {actual_count}"
        )
        return False


def migrate_all_data(database_url: str, data_dir: Path) -> None:
    """Migrate all datasets from JSON to PostgreSQL."""
    LOGGER.info("Starting data migration to Neon PostgreSQL...")
    
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
            
            # Migrate to database
            inserted = migrate_table(cursor, table_name, records)
            
            # Commit after each table
            connection.commit()
            
            # Verify migration
            if verify_migration(cursor, table_name, len(records)):
                migration_stats[table_name] = {
                    "source_count": len(records),
                    "inserted": inserted,
                    "status": "success"
                }
            else:
                migration_stats[table_name] = {
                    "source_count": len(records),
                    "inserted": inserted,
                    "status": "failed"
                }
        
        # Print summary
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)
        
        total_records = 0
        all_success = True
        
        for table_name, stats in migration_stats.items():
            status_icon = "✓" if stats["status"] == "success" else "✗"
            print(f"{status_icon} {table_name:15} {stats['inserted']:6} records")
            total_records += stats['inserted']
            if stats['status'] != "success":
                all_success = False
        
        print("="*70)
        print(f"Total records migrated: {total_records}")
        print("="*70)
        
        if all_success:
            LOGGER.info("\n✓ Data migration completed successfully!")
            LOGGER.info("\nNext steps:")
            LOGGER.info("  1. Update .env: SET USE_DATABASE=true")
            LOGGER.info("  2. Restart your application")
            LOGGER.info("  3. Test with: python -m app.cli 'How many customers do we have?'")
        else:
            LOGGER.error("\n✗ Some tables failed verification. Check logs above.")
            sys.exit(1)
        
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
    data_dir_path = os.getenv("DATA_DIR", "data/sample_data")
    
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
    print("\nThis will migrate data from JSON files to your Neon database.")
    print("Existing records with the same primary key will be skipped.")
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
