#!/usr/bin/env bash
set -euo pipefail

# Configure FleetPulse scheduled-feed settings for Azure App Service.
# This script creates Key Vault secrets for import keys and assigns App Service
# settings that reference those secrets. It never prints the secret values.

RG="${AZURE_RESOURCE_GROUP:-k1-fleetpulse-rg}"
APP_NAME="${AZURE_APP_NAME:-k1-fleetpulse}"
KV_NAME="${AZURE_KEY_VAULT_NAME:-kv-k1-fleetpulse}"

QBO_STATE_PATH="${FLEETPULSE_QBO_FINANCIAL_STATE_PATH:-/home/data/fleetpulse_qbo_financial.json}"
XCELERATOR_STATE_PATH="${FLEETPULSE_XCELERATOR_EVENT_STATE_PATH:-/home/data/fleetpulse_xcelerator_events.json}"
HR_STATE_PATH="${HR_RECRUITING_STATE_PATH:-/home/data/fleetpulse_hr_recruiting.json}"

random_secret() {
  openssl rand -base64 32 | tr -d '\n'
}

secret_value() {
  local secret_name="$1"
  local supplied_value="$2"

  if [[ -n "$supplied_value" ]]; then
    printf "%s" "$supplied_value"
    return
  fi

  local existing_value=""
  existing_value="$(
    az keyvault secret show \
      --vault-name "$KV_NAME" \
      --name "$secret_name" \
      --query value \
      -o tsv \
      2>/dev/null || true
  )"

  if [[ -n "$existing_value" ]]; then
    printf "%s" "$existing_value"
    return
  fi

  random_secret
}

QBO_IMPORT_KEY="$(secret_value FLEETPULSE-QBO-FINANCIAL-IMPORT-API-KEY "${FLEETPULSE_QBO_FINANCIAL_IMPORT_API_KEY:-}")"
XCELERATOR_IMPORT_KEY="$(secret_value FLEETPULSE-XCELERATOR-EVENT-IMPORT-API-KEY "${FLEETPULSE_XCELERATOR_EVENT_IMPORT_API_KEY:-}")"
HR_IMPORT_KEY="$(secret_value HR-RECRUITING-IMPORT-API-KEY "${HR_RECRUITING_IMPORT_API_KEY:-}")"

echo "Configuring App Service $APP_NAME in $RG with Key Vault $KV_NAME"

PRINCIPAL_ID="$(
  az webapp identity show \
    --name "$APP_NAME" \
    --resource-group "$RG" \
    --query principalId \
    -o tsv
)"

VAULT_ID="$(
  az keyvault show \
    --name "$KV_NAME" \
    --query id \
    -o tsv
)"

if [[ -n "$PRINCIPAL_ID" && -n "$VAULT_ID" ]]; then
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" \
    --scope "$VAULT_ID" \
    --only-show-errors \
    >/dev/null || true
fi

az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name FLEETPULSE-QBO-FINANCIAL-IMPORT-API-KEY \
  --value "$QBO_IMPORT_KEY" \
  --query id \
  -o tsv \
  >/dev/null

az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name FLEETPULSE-XCELERATOR-EVENT-IMPORT-API-KEY \
  --value "$XCELERATOR_IMPORT_KEY" \
  --query id \
  -o tsv \
  >/dev/null

az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name HR-RECRUITING-IMPORT-API-KEY \
  --value "$HR_IMPORT_KEY" \
  --query id \
  -o tsv \
  >/dev/null

az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --settings \
    WEBSITES_ENABLE_APP_SERVICE_STORAGE=true \
    FLEETPULSE_FINANCIAL_FEED_ENABLED=true \
    FLEETPULSE_QBO_FINANCIAL_STATE_PATH="$QBO_STATE_PATH" \
    FLEETPULSE_XCELERATOR_EVENT_STATE_PATH="$XCELERATOR_STATE_PATH" \
    FLEETPULSE_XCELERATOR_EVENT_RETAINED_RECORDS=50000 \
    HR_RECRUITING_STATE_PATH="$HR_STATE_PATH" \
    FLEETPULSE_QBO_FINANCIAL_IMPORT_API_KEY="@Microsoft.KeyVault(SecretUri=https://${KV_NAME}.vault.azure.net/secrets/FLEETPULSE-QBO-FINANCIAL-IMPORT-API-KEY)" \
    FLEETPULSE_XCELERATOR_EVENT_IMPORT_API_KEY="@Microsoft.KeyVault(SecretUri=https://${KV_NAME}.vault.azure.net/secrets/FLEETPULSE-XCELERATOR-EVENT-IMPORT-API-KEY)" \
    HR_RECRUITING_IMPORT_API_KEY="@Microsoft.KeyVault(SecretUri=https://${KV_NAME}.vault.azure.net/secrets/HR-RECRUITING-IMPORT-API-KEY)" \
  --only-show-errors \
  >/dev/null

echo "FleetPulse scheduled-feed app settings configured."
