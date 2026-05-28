# FleetPulse Azure Production Setup

Step-by-step guide to deploy FleetPulse on Azure App Service.

## Prerequisites

- Azure CLI installed (`az --version`)
- GitHub repo: `rami050480/FleetPulse`
- Your Geotab production credentials

## Step 1: Create Azure Resources (run once)

```bash
# Variables - change these
RG="k1-fleetpulse-rg"
LOCATION="southcentralus"
ACR_NAME="k1fleetpulseacr"
APP_NAME="k1-fleetpulse"
PLAN_NAME="k1-fleetpulse-plan"

# Login
az login

# Resource Group
az group create --name $RG --location $LOCATION

# Container Registry (Basic tier ~$5/mo)
az acr create --name $ACR_NAME --resource-group $RG --sku Basic --admin-enabled true

# App Service Plan (B1 ~$13/mo, good for start)
az appservice plan create \
  --name $PLAN_NAME \
  --resource-group $RG \
  --is-linux \
  --sku B1

# App Service (Docker container)
az webapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --plan $PLAN_NAME \
  --deployment-container-image-name $ACR_NAME.azurecr.io/fleetpulse:latest

# Set container port
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RG \
  --settings WEBSITES_PORT=8080

# Enable ACR pull from App Service
az webapp config container set \
  --name $APP_NAME \
  --resource-group $RG \
  --container-image-name $ACR_NAME.azurecr.io/fleetpulse:latest \
  --container-registry-url https://$ACR_NAME.azurecr.io \
  --container-registry-user $(az acr credential show --name $ACR_NAME --query username -o tsv) \
  --container-registry-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)
```

## Step 2: Set Geotab Credentials

```bash
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RG \
  --settings \
    GEOTAB_USERNAME="your_geotab_user" \
    GEOTAB_PASSWORD="your_geotab_pass" \
    GEOTAB_DATABASE="your_db_name" \
    GEOTAB_SERVER="my.geotab.com" \
    FLEETPULSE_ENV="production"
```

## Step 3: Configure GitHub Secrets

Go to `Settings > Secrets and variables > Actions` in your repo and add:

| Secret | How to get it |
|--------|---------------|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --name k1-fleetpulse-sp --role contributor --scopes /subscriptions/{sub-id}/resourceGroups/k1-fleetpulse-rg --json-auth` |
| `ACR_LOGIN_SERVER` | `k1fleetpulseacr.azurecr.io` |
| `ACR_USERNAME` | `az acr credential show --name k1fleetpulseacr --query username -o tsv` |
| `ACR_PASSWORD` | `az acr credential show --name k1fleetpulseacr --query passwords[0].value -o tsv` |
| `AZURE_RESOURCE_GROUP` | `k1-fleetpulse-rg` |
| `AZURE_APP_NAME` | `k1-fleetpulse` |

## Step 4: Deploy

Push to `main` and GitHub Actions will:
1. Build the Docker image (frontend + backend)
2. Push to ACR
3. Deploy to App Service
4. Run health check smoke test

Or trigger manually: Actions tab > Deploy to Azure App Service > Run workflow.

## Step 5: Verify

```bash
curl https://k1-fleetpulse.azurewebsites.net/api/health
curl https://k1-fleetpulse.azurewebsites.net/api/dashboard/overview
```

Open `https://k1-fleetpulse.azurewebsites.net` in browser to see the dashboard.

### Optional: Address Benchmark Scan Settings

The pickup/delivery history scan is read-only. Xcelerator remains the source of
truth for pickup/delivery addresses, timestamps, revenue, and driver pay. The
optional evidence file is a read-only export of voice/email context; FleetPulse
does not connect to or write back to Outlook, Teams, SharePoint, Google Drive,
Geotab, or Xcelerator from this scan.

```bash
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RG \
  --settings \
    FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE="auto" \
    FLEETPULSE_ADDRESS_BENCHMARK_PERIOD_DAYS="180" \
    FLEETPULSE_ADDRESS_BENCHMARK_STOP_THRESHOLD_MINUTES="60" \
    FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES="2" \
    FLEETPULSE_ADDRESS_BENCHMARK_MAX_PAIRS="50" \
    FLEETPULSE_ADDRESS_BENCHMARK_MAX_RECENT_ORDERS_PER_PAIR="5" \
    FLEETPULSE_ADDRESS_BENCHMARK_MAX_SOURCE_ROWS="5000" \
    FLEETPULSE_ADDRESS_BENCHMARK_TIMEZONE="America/Chicago" \
    FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH="" \
    FLEETPULSE_ADDRESS_BENCHMARK_COST_PER_TRUCK_HOUR=""
```

If the scan should read Fabric Warehouse SQL directly, configure
`FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*` through App Settings or Key Vault
references. When those values are omitted, FleetPulse falls back to the
ReviewOrders state path.

## Step 6: MCP Server (local, points to Azure)

Update `mcp-server/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fleetpulse": {
      "command": "python",
      "args": ["mcp-server/server.py"],
      "cwd": "/path/to/FleetPulse",
      "env": {
        "FLEETPULSE_API_URL": "https://k1-fleetpulse.azurewebsites.net/api"
      }
    }
  }
}
```

## Step 7: Enable Application Insights (optional)

```bash
az monitor app-insights component create \
  --app k1-fleetpulse-insights \
  --location $LOCATION \
  --resource-group $RG

# Get instrumentation key and set it
IKEY=$(az monitor app-insights component show --app k1-fleetpulse-insights --resource-group $RG --query instrumentationKey -o tsv)

az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RG \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY=$IKEY
```

## Estimated Monthly Cost

| Resource | SKU | Cost |
|----------|-----|------|
| App Service Plan | B1 | ~$13 |
| Container Registry | Basic | ~$5 |
| App Insights | Free tier | $0 |
| **Total** | | **~$18/mo** |
