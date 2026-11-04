#!/usr/bin/env bash
# Deploys the Customs Copilot API on Azure Container Apps. Run it in Azure Cloud Shell (Bash): portal.azure.com, the ">_" icon at the top.
#
#   curl -fsSL https://raw.githubusercontent.com/Maaz5711/customs-copilot/main/deploy/azure/deploy.sh -o deploy.sh && bash deploy.sh
#
# You need: (1) the data zip uploaded to a PRIVATE Azure blob and a read-only SAS link to it, (2) your DeepSeek key.
# Both are asked for with hidden input and stored as Container Apps secrets. Nothing is printed or saved to a file.
set -euo pipefail

IMAGE="ghcr.io/maaz5711/customs-copilot-api:latest"     # built by GitHub Actions from the public repository (code only)
APP="customs-copilot-api"
ENVNAME="customs-env"

read -rp "Resource group name [customs-rg]: " RG; RG="${RG:-customs-rg}"
echo "Azure for Students only allows some regions. Common ones: uaenorth, centralindia, southeastasia, westeurope, swedencentral."
read -rp "Region: " LOC
read -rsp "Paste the Blob SAS URL of customs-copilot-data.zip (hidden): " DATA_URL; echo
read -rsp "Paste the SHA-256 printed by pack_data.py (hidden, or press Enter to skip): " DATA_SHA; echo
read -rsp "Paste your DeepSeek API key (hidden): " DS_KEY; echo
[ -n "$DATA_URL" ] && [ -n "$DS_KEY" ] || { echo "The data link and the key are both required."; exit 1; }

az extension add --name containerapp --upgrade --only-show-errors -y >/dev/null
az provider register --namespace Microsoft.App --wait >/dev/null
az provider register --namespace Microsoft.OperationalInsights --wait >/dev/null
az group create --name "$RG" --location "$LOC" --output none
az containerapp env create --name "$ENVNAME" --resource-group "$RG" --location "$LOC" --output none

SECRETS=(dataurl="$DATA_URL" deepseek="$DS_KEY")
ENVVARS=(DATA_ZIP_URL=secretref:dataurl DEEPSEEK_API_KEY=secretref:deepseek API_MAX_LLM_CALLS=1000 LLM_PROVIDER=deepseek)
if [ -n "$DATA_SHA" ]; then SECRETS+=(datasha="$DATA_SHA"); ENVVARS+=(DATA_ZIP_SHA256=secretref:datasha); fi

# 1 CPU and 2 GiB of memory (the API needs about 0.9 GB once its models are loaded); one instance at most (conversations live in memory, and it caps spending)
az containerapp create --name "$APP" --resource-group "$RG" --environment "$ENVNAME" --image "$IMAGE" \
  --ingress external --target-port 8080 --cpu 1 --memory 2.0Gi --min-replicas 0 --max-replicas 1 \
  --secrets "${SECRETS[@]}" --env-vars "${ENVVARS[@]}" --output none

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn --output tsv)"
echo
echo "Done. Your API address is:  https://$FQDN"
echo "Test it in a browser:       https://$FQDN/api/meta   (the first visit takes about a minute while it starts and downloads the data)"
echo "Send me the address above (it is not secret)."
