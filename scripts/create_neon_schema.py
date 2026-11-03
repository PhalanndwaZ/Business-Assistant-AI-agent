"""Create database schema in Neon PostgreSQL for business data tables."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

# SQL statements for schema creation
SCHEMA_STATEMENTS = [
    # Drop existing tables (careful - this deletes data!)
    """
    DROP TABLE IF EXISTS order_items CASCADE;
    DROP TABLE IF EXISTS orders CASCADE;
    DROP TABLE IF EXISTS products CASCADE;
    DROP TABLE IF EXISTS customers CASCADE;
    DROP TABLE IF EXISTS employees CASCADE;
    """,
    
    # Create customers table
    """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id VARCHAR(10) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        region VARCHAR(50) NOT NULL,
        segment VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    
    # Create products table
    """
    CREATE TABLE IF NOT EXISTS products (
        product_id VARCHAR(10) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        category VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    
    # Create orders table
    """
    CREATE TABLE IF NOT EXISTS orders (
        order_id VARCHAR(10) PRIMARY KEY,
        customer_id VARCHAR(10) NOT NULL,
        order_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_orders_customer
            FOREIGN KEY (customer_id) 
            REFERENCES customers(customer_id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE
    );
    """,
    
    # Create order_items table
    """
    CREATE TABLE IF NOT EXISTS order_items (
        order_id VARCHAR(10) NOT NULL,
        product_id VARCHAR(10) NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (order_id, product_id),
        CONSTRAINT fk_order_items_order
            FOREIGN KEY (order_id) 
            REFERENCES orders(order_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE,
        CONSTRAINT fk_order_items_product
            FOREIGN KEY (product_id) 
            REFERENCES products(product_id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE
    );
    """,
    
    # Create employees table
    """
    CREATE TABLE IF NOT EXISTS employees (
        employee_id VARCHAR(10) PRIMARY KEY,
        department VARCHAR(50) NOT NULL,
        job_title VARCHAR(100) NOT NULL,
        hire_date DATE NOT NULL,
        manager_id VARCHAR(10),
        salary_cents INTEGER NOT NULL CHECK (salary_cents >= 0),
        performance_rating INTEGER NOT NULL CHECK (performance_rating BETWEEN 1 AND 5),
        work_email VARCHAR(100) NOT NULL UNIQUE,
        phone VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_employees_manager
            FOREIGN KEY (manager_id) 
            REFERENCES employees(employee_id)
            ON DELETE SET NULL
            ON UPDATE CASCADE
    );
    """,
    
    # Create indexes for performance
    """
    CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
    CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);
    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
    CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
    CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
    CREATE INDEX IF NOT EXISTS idx_employees_manager_id ON employees(manager_id);
    CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department);
    CREATE INDEX IF NOT EXISTS idx_employees_hire_date ON employees(hire_date);
    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
    CREATE INDEX IF NOT EXISTS idx_customers_region ON customers(region);
    CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers(segment);
    """,
]


def create_schema(database_url: str, *, drop_existing: bool = False) -> None:
    """Create all database tables, constraints, and indexes."""
    if not database_url:
        raise ValueError("NEON_DATABASE_URL environment variable is not set")
    
    LOGGER.info("Connecting to Neon PostgreSQL database...")
    
    try:
        connection = psycopg2.connect(database_url)
        connection.autocommit = True
        cursor = connection.cursor()
        
        LOGGER.info("Connected successfully to database")
        
        if drop_existing:
            LOGGER.warning("Dropping existing tables (this will delete all data)...")
            cursor.execute(SCHEMA_STATEMENTS[0])
            LOGGER.info("Existing tables dropped")
            statements_to_run = SCHEMA_STATEMENTS[1:]
        else:
            LOGGER.info("Creating schema without dropping existing tables...")
            statements_to_run = SCHEMA_STATEMENTS[1:]
        
        # Create tables
        for idx, statement in enumerate(statements_to_run, 1):
            statement = statement.strip()
            if not statement:
                continue
            
            try:
                cursor.execute(statement)
                # Extract table name for logging
                if "CREATE TABLE IF NOT EXISTS" in statement:
                    table_name = (
                        statement.split("CREATE TABLE IF NOT EXISTS", 1)[1]
                        .split("(", 1)[0]
                        .strip()
                    )
                    LOGGER.info("✓ Ensured table: %s", table_name)
                elif "CREATE INDEX IF NOT EXISTS" in statement:
                    index_name = (
                        statement.split("CREATE INDEX IF NOT EXISTS", 1)[1]
                        .split("ON", 1)[0]
                        .strip()
                    )
                    LOGGER.info("✓ Ensured index: %s", index_name)
            except psycopg2.Error as exc:
                LOGGER.error(f"Failed to execute statement {idx}: {exc}")
                raise
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        LOGGER.info(f"\n✓ Schema creation complete!")
        LOGGER.info(f"✓ Created {len(tables)} tables: {', '.join(tables)}")
        
        # Get index count
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """)
        index_count = cursor.fetchone()[0]
        LOGGER.info(f"✓ Created {index_count} indexes")
        
        cursor.close()
        connection.close()
        
        LOGGER.info("\n✓ Database schema is ready for data migration!")
        
    except psycopg2.Error as exc:
        LOGGER.error(f"Database error: {exc}")
        sys.exit(1)
    except Exception as exc:
        LOGGER.error(f"Unexpected error: {exc}")
        sys.exit(1)


def main() -> None:
    """Load configuration and create database schema."""
    load_dotenv(PROJECT_ROOT / ".env")
    
    database_url = os.getenv("NEON_DATABASE_URL", "").strip()
    
    if not database_url:
        LOGGER.error(
            "NEON_DATABASE_URL is not set in .env file. "
            "Please add your Neon PostgreSQL connection string."
        )
        sys.exit(1)
    
    # Ask for confirmation before dropping tables
    print("\n" + "="*70)
    print("DATABASE SCHEMA MIGRATION")
    print("="*70)
    print("\nThis script will create the following tables in your Neon database:")
    print("  - customers")
    print("  - products")
    print("  - orders")
    print("  - order_items")
    print("  - employees")
    print("\nIt will also create indexes for optimal query performance.")
    print("\n⚠️  WARNING: If you choose to drop existing tables, ALL DATA will be LOST!")
    print("="*70)
    
    response = input("\nDo you want to DROP existing tables first? (yes/no): ").strip().lower()
    drop_existing = response in ("yes", "y")
    
    if drop_existing:
        confirm = input("\n⚠️  Are you ABSOLUTELY SURE? This cannot be undone! (type 'DELETE' to confirm): ").strip()
        if confirm != "DELETE":
            LOGGER.info("Operation cancelled by user")
            sys.exit(0)
    
    try:
        create_schema(database_url, drop_existing=drop_existing)
        print("\n✓ Schema migration completed successfully!")
        print("\nNext steps:")
        print("  1. Run: python scripts/migrate_data_to_neon.py")
        print("  2. Update .env: SET USE_DATABASE=true")
        print("  3. Restart your application")
        
    except Exception as exc:
        LOGGER.error(f"Schema migration failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
