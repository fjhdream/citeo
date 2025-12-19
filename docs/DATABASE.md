# Database Configuration Guide

Citeo supports multiple database backends for storing paper data. You can choose between SQLite (local) and Cloudflare D1 (edge-deployed) databases.

## Supported Databases

### 1. SQLite (Default)

**Use Case:** Local development, single-server deployments

**Advantages:**
- Zero setup required
- No external dependencies
- File-based storage
- Perfect for development and small deployments

**Configuration:**
```env
DB_TYPE=sqlite
DB_PATH=data/citeo.db
```

### 2. Cloudflare D1

**Use Case:** Production deployments, global edge applications

**Advantages:**
- Globally distributed SQLite
- Low latency worldwide
- Integrated with Cloudflare Workers
- Serverless and scalable

**Configuration:**
```env
DB_TYPE=d1
D1_ACCOUNT_ID=your-cloudflare-account-id
D1_DATABASE_ID=your-d1-database-id
D1_API_TOKEN=your-cloudflare-api-token
```

## Setting Up Cloudflare D1

### Step 1: Create a D1 Database

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Navigate to **Workers & Pages** → **D1 SQL Database**
3. Click **Create database**
4. Enter a name (e.g., `citeo-production`)
5. Click **Create**

### Step 2: Get Your Credentials

After creating the database, you'll need:

1. **Account ID**: Found in the URL or dashboard home
   - Example: `https://dash.cloudflare.com/{account-id}/workers/d1`

2. **Database ID**: Found in the D1 database details page
   - Click on your database name to see the Database ID

3. **API Token**: Create a token with D1 permissions
   - Go to **My Profile** → **API Tokens**
   - Click **Create Token**
   - Use the **Edit Cloudflare Workers** template
   - Or create a custom token with these permissions:
     - Account → D1 → Edit
   - Save the token (you won't be able to see it again!)

### Step 3: Initialize the Database Schema

Run the initialization script to create tables:

```bash
# Using wrangler CLI (recommended)
wrangler d1 execute citeo-production --file=src/citeo/storage/migrations/init_schema.sql

# Or use the Cloudflare Dashboard:
# 1. Go to your D1 database
# 2. Click "Console"
# 3. Paste the contents of init_schema.sql
# 4. Execute
```

### Step 4: Configure Your Application

Update your `.env` file:

```env
DB_TYPE=d1
D1_ACCOUNT_ID=abc123def456ghi789
D1_DATABASE_ID=12345678-1234-1234-1234-123456789abc
D1_API_TOKEN=your-secret-api-token-here
```

### Step 5: Test the Connection

Run the test script to verify your configuration:

```bash
uv run python scripts/test_database_switch.py
```

## Switching Between Databases

To switch between SQLite and D1, simply change the `DB_TYPE` environment variable:

**Switch to SQLite:**
```env
DB_TYPE=sqlite
```

**Switch to D1:**
```env
DB_TYPE=d1
```

No code changes are required. The application automatically uses the correct storage adapter based on your configuration.

## API Usage

### D1 REST API Endpoint

The D1 adapter uses Cloudflare's REST API:
```
POST https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query
```

**Headers:**
- `Authorization: Bearer {api_token}`
- `Content-Type: application/json`

**Payload:**
```json
{
  "sql": "SELECT * FROM papers WHERE arxiv_id = ?",
  "params": ["2512.14709"]
}
```

## Performance Considerations

### SQLite
- **Read/Write:** Very fast for local operations
- **Latency:** <1ms (local disk)
- **Scale:** Single server, up to millions of records

### Cloudflare D1
- **Read/Write:** Fast globally (edge locations)
- **Latency:** 10-50ms (varies by region)
- **Scale:** Distributed, handles global traffic

## Troubleshooting

### D1 Connection Errors

**Error:** `D1 query failed: Authentication error`
- **Solution:** Check your API token has D1 permissions

**Error:** `D1_ACCOUNT_ID is required when DB_TYPE=d1`
- **Solution:** Ensure all required D1 environment variables are set

**Error:** `HTTP 404 Not Found`
- **Solution:** Verify your Account ID and Database ID are correct

### Migration Issues

If you need to migrate data from SQLite to D1:

1. Export data from SQLite:
   ```bash
   sqlite3 data/citeo.db .dump > backup.sql
   ```

2. Clean up SQLite-specific syntax (if needed)

3. Import to D1:
   ```bash
   wrangler d1 execute citeo-production --file=backup.sql
   ```

## Best Practices

1. **Development:** Use SQLite for faster iteration
2. **Production:** Use D1 for edge deployments and global reach
3. **Backups:** Regularly export D1 data using wrangler CLI
4. **Monitoring:** Check Cloudflare Analytics for D1 usage and performance

## Additional Resources

- [Cloudflare D1 Documentation](https://developers.cloudflare.com/d1/)
- [D1 REST API Reference](https://developers.cloudflare.com/api/operations/cloudflare-d1-query-database)
- [Wrangler CLI Documentation](https://developers.cloudflare.com/workers/wrangler/)
