# Neon PostgreSQL Migration Guide

This guide explains how to seed and use Neon PostgreSQL for the Business
Assistant AI. The checked-in JSON snapshots are isolated under
`tests/fixtures/business_data` for migration and offline validation.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Overview

The application now supports **two data storage modes**:

1. **Database Mode (Default)** - Connects to Neon PostgreSQL for business-data access
2. **JSON Mode (Legacy/Test)** - Loads fixture data from `tests/fixtures/business_data/*.json`

You can toggle between modes using the `USE_DATABASE` environment variable.

### Benefits of Using Neon PostgreSQL

- ✅ **Real-time updates** - No need to regenerate JSON files
- ✅ **Better performance** - Indexed queries and connection pooling
- ✅ **Concurrent access** - Multiple users can query simultaneously
- ✅ **ACID compliance** - Data integrity guarantees
- ✅ **Serverless scaling** - Neon handles automatic scaling
- ✅ **Database branching** - Easy dev/staging/production environments

---

## Prerequisites

1. **Python 3.10+** with virtual environment activated
2. **Neon Account** - Sign up at [neon.tech](https://neon.tech) (free tier available)
3. **Updated dependencies** - Run: `pip install -r requirements.txt`

---

## Quick Start

### Step 1: Create Neon Database

1. Go to [neon.tech](https://neon.tech) and create a free account
2. Create a new project (or use existing one)
3. Copy your connection string (looks like: `postgresql://user:pass@ep-xxxxx.neon.tech/dbname?sslmode=require`)

### Step 2: Configure Environment

Update your `.env` file:

```env
# Enable database mode
USE_DATABASE=true

# Add your Neon connection string
NEON_DATABASE_URL=postgresql://username:password@ep-xxxxx.neon.tech/dbname?sslmode=require

# Optional: Connection pool settings
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
```

### Step 3: Run Migration Scripts

```powershell
# 1. Create database schema (tables, indexes, foreign keys)
python scripts/create_neon_schema.py

# 2. Seed Neon from the retained migration fixtures
python scripts/migrate_data_to_neon.py
```

### Step 4: Test the Connection

```powershell
# Test with CLI
python -m app.cli "How many customers do we have?"

# Or start the API
python -m uvicorn main:app --reload
```

**That's it!** Your application is now using Neon PostgreSQL. 🎉

---

## Detailed Setup

### Database Schema

The migration creates 5 tables:

| Table | Primary Key | Records | Description |
|-------|-------------|---------|-------------|
| `customers` | customer_id | 60 | Customer information |
| `products` | product_id | 30 | Product catalog |
| `orders` | order_id | 961 | Order records |
| `order_items` | (order_id, product_id) | 1,871 | Order line items |
| `employees` | employee_id | 15 | Employee data |

Counts above reflect the retained fixtures at the time this guide was updated.
The migration reads `tests/fixtures/business_data` unless `DATA_DIR` overrides
that source path.

**Relationships:**
- `orders.customer_id` → `customers.customer_id`
- `order_items.order_id` → `orders.order_id`
- `order_items.product_id` → `products.product_id`
- `employees.manager_id` → `employees.employee_id` (self-referencing)

**Indexes created for performance:**
- Orders: `customer_id`, `order_date`, `status`
- Order items: `order_id`, `product_id`
- Employees: `manager_id`, `department`, `hire_date`
- Products: `category`
- Customers: `region`, `segment`

### Migration Scripts

#### 1. `scripts/create_neon_schema.py`

Creates all database tables, foreign keys, and indexes.

**Options:**
- **Drop existing tables:** Removes all data and recreates schema
- **Keep existing tables:** Only creates missing tables

**Safety features:**
- Confirmation prompts before destructive operations
- Validates table creation
- Reports index count

**Run it:**
```powershell
python scripts/create_neon_schema.py
```

#### 2. `scripts/migrate_data_to_neon.py`

Seeds or refreshes Neon from the retained JSON fixtures.

**Features:**
- Respects foreign key dependencies
- Batch inserts for performance (100 records per batch)
- Inserts new records and updates matching primary keys from JSON
- Uses each database table's primary key, including the composite order-item key
- Verifies that every JSON source key exists after migration; extra database
  rows do not cause verification to fail
- Runs as one transaction and rolls back if verification fails
- Does not delete database rows absent from the JSON source
- Shows detailed progress and summary

**Run it:**
```powershell
python scripts/migrate_data_to_neon.py
```

**Expected output:**
```
✓ customers        60 source records
✓ products         30 source records
✓ employees        15 source records
✓ orders          961 source records
✓ order_items    1871 source records
================================
Total source records inserted or updated: 2937
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `USE_DATABASE` | No | `true` | Use Neon PostgreSQL for business-data queries |
| `NEON_DATABASE_URL` | Yes (if USE_DATABASE=true) | - | Neon connection string |
| `DATABASE_POOL_SIZE` | No | `5` | Minimum connections in pool |
| `DATABASE_MAX_OVERFLOW` | No | `10` | Maximum additional connections |
| `DATA_DIR` | No | `tests/fixtures/business_data` | Migration and evaluation fixture directory |

### Connection String Format

```
postgresql://[user]:[password]@[host]/[database]?sslmode=require
```

**Example:**
```
postgresql://myuser:mypassword@ep-cool-name-123456.us-east-2.aws.neon.tech/mydb?sslmode=require
```

**Where to find it:**
1. Log in to [Neon Console](https://console.neon.tech)
2. Select your project
3. Go to "Connection Details"
4. Copy the connection string

### Switching Between Modes

To switch back to JSON mode:
```env
USE_DATABASE=false
```

To switch to database mode:
```env
USE_DATABASE=true
```

**No code changes needed!** The application automatically detects the mode.

---

## Troubleshooting

### Connection Issues

**Problem:** `Failed to connect to Neon PostgreSQL`

**Solutions:**
1. Verify your connection string is correct
2. Check that `sslmode=require` is included
3. Ensure your Neon project is active (not suspended)
4. Test connection with `psql`:
   ```powershell
   psql "postgresql://user:pass@ep-xxxxx.neon.tech/dbname?sslmode=require"
   ```

### Schema Migration Errors

**Problem:** `Missing required tables in database`

**Solution:** Run the schema creation script first:
```powershell
python scripts/create_neon_schema.py
```

**Problem:** `Table already exists`

**Solution:** Use the drop option or manually drop tables:
```sql
DROP TABLE IF EXISTS order_items, orders, products, customers, employees CASCADE;
```

### Data Migration Issues

**Problem:** `Foreign key violation`

**Solution:** The migration script handles dependencies automatically. If you see this error:
1. Drop all tables and recreate schema
2. Run data migration again

**Problem:** `Duplicate key value violates unique constraint`

**Solution:** The script upserts records using the target table primary key and
verifies that all source keys exist. Rows present only in Neon are retained,
and matching JSON records update their values.

### Performance Issues

**Problem:** Slow queries

**Solutions:**
1. Increase connection pool size in `.env`:
   ```env
   DATABASE_POOL_SIZE=10
   DATABASE_MAX_OVERFLOW=20
   ```
2. Check Neon compute status (might be in idle state)
3. Verify indexes were created:
   ```sql
   SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public';
   ```

### Application Errors

**Problem:** `NEON_DATABASE_URL is not set`

**Solution:** Add the connection string to your `.env` file

**Problem:** `Module 'psycopg2' has no attribute 'pool'`

**Solution:** Reinstall dependencies:
```powershell
pip install --upgrade --force-reinstall psycopg2-binary
```

---

## FAQ

### Q: Can I use both modes simultaneously?

**A:** No, the application uses either JSON or database mode at a time. However, you can switch between modes by changing `USE_DATABASE` in `.env` and restarting.

### Q: Will my JSON files be deleted?

**A:** The business-data snapshots were moved out of `data/sample_data` into
`tests/fixtures/business_data`. They remain available for migration and offline
evaluation, but Neon is the live source when `USE_DATABASE=true`.

### Q: How do I update data in the database?

**A:** You can:
1. Connect directly with `psql` or a database client
2. Use SQL UPDATE statements
3. Re-run the migration script (skips duplicates)
4. Use database management tools like DBeaver or pgAdmin

### Q: Can I use a different PostgreSQL provider?

**A:** Yes! The code works with any PostgreSQL database. Just update `NEON_DATABASE_URL` with your connection string:
- AWS RDS PostgreSQL
- Google Cloud SQL
- Azure Database for PostgreSQL
- Self-hosted PostgreSQL

### Q: How do I reset the database?

**A:** Run the schema script with the drop option:
```powershell
python scripts/create_neon_schema.py
# Choose "yes" when prompted to drop tables
```

Then re-run the data migration:
```powershell
python scripts/migrate_data_to_neon.py
```

### Q: What about the vector store and documents?

**A:** Document search (RAG) is independent and still uses:
- `data/documents/` for source files
- `data/vector_store/chunks.json` for embeddings
- No migration needed for these components

### Q: Does this affect the frontend?

**A:** No changes needed! The frontend communicates with the API, which transparently uses either data source.

### Q: What about the conversation history?

**A:** Conversation history uses SQLite (`data/conversations.sqlite3`) and is separate from business data. No migration needed.

### Q: How do I backup my Neon database?

**A:** Neon provides automatic backups. You can also:
1. Use Neon's branching feature to create snapshots
2. Export with `pg_dump`:
   ```powershell
   pg_dump "postgresql://..." > backup.sql
   ```
3. Use Neon's Point-in-Time Recovery (PITR) feature

### Q: What's the cost of Neon?

**A:** Neon offers:
- **Free tier:** 0.5 GB storage, 1 compute hour/month
- **Paid plans:** Scale as you grow with usage-based pricing
- Check [neon.tech/pricing](https://neon.tech/pricing)

### Q: Can I use Neon branches for development?

**A:** Yes! This is one of Neon's best features:
1. Create a branch for testing
2. Update `NEON_DATABASE_URL` to point to branch
3. Test changes safely
4. Merge or discard as needed

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Application Layer                     │
│  (FastAPI, CLI, MCP Server, LangGraph)                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Data Access Layer   │
         │  (get_store function) │
         └───────────┬───────────┘
                     │
        ┌────────────┴─────────────┐
        │                          │
        ▼                          ▼
┌──────────────────┐    ┌────────────────────┐
│  JsonDataStore   │    │ PostgresDataStore  │
│  (Legacy Mode)   │    │  (Database Mode)   │
└────────┬─────────┘    └─────────┬──────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐    ┌────────────────────┐
│   JSON Files     │    │  Neon PostgreSQL   │
│ tests/fixtures/  │───▶│ Neon PostgreSQL    │
└──────────────────┘    └────────────────────┘
```

Both data stores expose the same interface:
- `get_frame(dataset_name) -> pd.DataFrame`
- `dataset_names -> tuple[str, ...]`

This allows seamless switching between modes.

---

## Next Steps

1. ✅ **Verify migration** - Run test queries
2. ✅ **Monitor performance** - Check Neon dashboard
3. ✅ **Update .env** - Set `USE_DATABASE=true` in production
4. 📊 **Scale as needed** - Upgrade Neon plan if needed
5. 🔄 **Enable branching** - Use for dev/staging environments

---

## Support

- **Neon Documentation:** [neon.tech/docs](https://neon.tech/docs)
- **PostgreSQL Docs:** [postgresql.org/docs](https://www.postgresql.org/docs/)
- **Project Issues:** Check application logs and error messages

---

## Summary

You've successfully migrated from JSON files to Neon PostgreSQL! 🚀

**Key Commands:**
```powershell
# Create schema
python scripts/create_neon_schema.py

# Migrate data
python scripts/migrate_data_to_neon.py

# Test
python -m app.cli "How many customers do we have?"
```

**Remember:**
- Set `USE_DATABASE=true` in `.env`
- Keep `NEON_DATABASE_URL` secure
- JSON files remain as backup
- No frontend changes needed

Happy querying! 📊
