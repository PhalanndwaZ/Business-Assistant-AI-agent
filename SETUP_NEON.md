# Quick Neon Setup Guide

## Step 1: Create Neon Account & Get Connection String

1. **Go to** [neon.tech](https://neon.tech)
2. **Click** "Sign Up" (it's FREE - no credit card required)
3. **Verify** your email
4. **Create a new project:**
   - Click "Create Project"
   - Name it: "Business-Assistant-AI" (or any name you like)
   - Select region: Choose closest to you
   - Click "Create Project"

5. **Copy your connection string:**
   - You'll see a connection string that looks like:
   ```
   postgresql://username:password@ep-xxxxx-xxxxx.region.aws.neon.tech/dbname?sslmode=require
   ```
   - **IMPORTANT:** Copy this entire string! You'll need it next.

## Step 2: Configure Your .env File

Open your `.env` file and add:

```env
# Enable database mode
USE_DATABASE=true

# Paste your Neon connection string here:
NEON_DATABASE_URL=postgresql://your-username:your-password@ep-xxxxx.neon.tech/neondb?sslmode=require
```

**Example of what it should look like:**
```env
USE_DATABASE=true
NEON_DATABASE_URL=postgresql://myuser:abc123xyz@ep-cool-sky-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
```

## Step 3: Run Migration Scripts

Once you have your connection string in `.env`, run these commands:

```powershell
# Create the database schema
python scripts/create_neon_schema.py

# Migrate the data
python scripts/migrate_data_to_neon.py
```

## Need Help?

If you don't have a Neon account yet or need help:
1. I can guide you through the setup
2. Or you can use the existing JSON mode for now (set `USE_DATABASE=false`)

Ready to proceed? Just let me know when you have your Neon connection string!
