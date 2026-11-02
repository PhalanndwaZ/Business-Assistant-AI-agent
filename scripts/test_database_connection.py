"""Test database connection and verify data."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_access.postgres_loader import PostgresDataStore

def test_connection():
    """Test Neon database connection and query data."""
    load_dotenv(PROJECT_ROOT / ".env")
    
    print("="*70)
    print("TESTING NEON DATABASE CONNECTION")
    print("="*70)
    
    database_url = os.getenv("NEON_DATABASE_URL", "").strip()
    if not database_url:
        print("❌ NEON_DATABASE_URL not set in .env")
        sys.exit(1)
    
    print("\n1. Connecting to Neon PostgreSQL...")
    try:
        store = PostgresDataStore(database_url)
        print("✓ Connection successful!")
    except Exception as exc:
        print(f"❌ Connection failed: {exc}")
        sys.exit(1)
    
    print("\n2. Testing data queries...")
    print("-" * 70)
    
    # Test each dataset
    datasets = ["customers", "products", "employees", "orders", "order_items"]
    
    for dataset_name in datasets:
        try:
            df = store.get_frame(dataset_name)
            print(f"✓ {dataset_name:15} {len(df):4} rows loaded")
        except Exception as exc:
            print(f"❌ {dataset_name:15} Failed: {exc}")
    
    print("-" * 70)
    
    # Show sample data from customers
    print("\n3. Sample customer data:")
    try:
        customers_df = store.get_frame("customers")
        print(customers_df.head(5).to_string(index=False))
    except Exception as exc:
        print(f"❌ Failed to load sample data: {exc}")
    
    # Show summary statistics
    print("\n4. Data summary:")
    print("-" * 70)
    try:
        customers_df = store.get_frame("customers")
        print(f"Total customers: {len(customers_df)}")
        print(f"Regions: {customers_df['region'].nunique()}")
        print(f"Segments: {customers_df['segment'].nunique()}")
        
        orders_df = store.get_frame("orders")
        print(f"\nTotal orders: {len(orders_df)}")
        print(f"Completed orders: {len(orders_df[orders_df['status'] == 'completed'])}")
        
        products_df = store.get_frame("products")
        print(f"\nTotal products: {len(products_df)}")
        print(f"Categories: {products_df['category'].nunique()}")
        
    except Exception as exc:
        print(f"❌ Failed to generate summary: {exc}")
    
    print("\n" + "="*70)
    print("✓ DATABASE CONNECTION TEST PASSED!")
    print("="*70)
    print("\nYour application is now using Neon PostgreSQL! 🎉")
    print("\nNext steps:")
    print("  • Start the API: python -m uvicorn main:app --reload")
    print("  • Test frontend: npm --prefix frontend run dev")
    print("  • Monitor queries in Neon dashboard")
    
    # Clean up
    store.close()


if __name__ == "__main__":
    test_connection()
