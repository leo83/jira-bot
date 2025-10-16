# Kubernetes Deployment Guide

This guide explains how to deploy the Jira Bot to Kubernetes.

## Prerequisites

- Kubernetes cluster
- `kubectl` configured to access your cluster
- Docker image `jira-bot:latest` built and available in your cluster

## Deployment Steps

### 1. Build and Push Docker Image

First, build the Docker image:

```bash
# Build the image
docker build -t jira-bot:latest .

# Tag for your registry (replace with your registry)
docker tag jira-bot:latest your-registry.com/jira-bot:latest

# Push to registry
docker push your-registry.com/jira-bot:latest
```

### 2. Create Secrets

Create the secrets file with your actual values:

```bash
# Create secrets file
cp k8s-secrets.yaml k8s-secrets-prod.yaml

# Edit the file and replace the empty values with base64 encoded secrets
# To encode: echo -n "your_value" | base64
```

Example of encoding secrets:

```bash
# Encode your secrets
echo -n "your_telegram_bot_token" | base64
echo -n "your_jira_username" | base64
echo -n "your_jira_api_token" | base64
```

Update `k8s-secrets-prod.yaml` with the encoded values.

### 3. Deploy to Kubernetes

```bash
# Apply secrets
kubectl apply -f k8s-secrets-prod.yaml

# Apply deployment
kubectl apply -f k8s-deployment-only.yaml
```

### 4. Verify Deployment

```bash
# Check deployment status
kubectl get deployments

# Check pod status
kubectl get pods -l app=jira-bot

# Check logs
kubectl logs -l app=jira-bot

# Check service
kubectl get services
```

## Configuration

### Environment Variables

The deployment uses the following environment variables:

- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token (from secret)
- `JIRA_USERNAME` - Your Jira username (from secret)
- `JIRA_API_TOKEN` - Your Jira API token (from secret)
- `JIRA_URL` - Jira server URL (default: https://myteam.aeroclub.ru)
- `JIRA_PROJECT_KEY` - Project key (default: AAI)
- `JIRA_COMPONENT_NAME` - Component name (default: org)
- `ALLOWED_USERS` - Comma-separated list of authorized users (empty = allow all)

### Resource Limits

- **Memory**: 64Mi request, 128Mi limit
- **CPU**: 50m request, 100m limit

### Health Checks

- **Liveness Probe**: Checks Telegram API connectivity every 60 seconds
- **Readiness Probe**: Checks Telegram API connectivity every 30 seconds

## Scaling

To scale the deployment:

```bash
# Scale to 3 replicas
kubectl scale deployment jira-bot --replicas=3

# Or edit the deployment
kubectl edit deployment jira-bot
```

## Monitoring

```bash
# View pod logs
kubectl logs -f deployment/jira-bot

# View pod status
kubectl describe pod -l app=jira-bot

# Check resource usage
kubectl top pods -l app=jira-bot
```

## Troubleshooting

### Common Issues

1. **Pod not starting**: Check secrets are properly encoded
2. **Bot not responding**: Verify Telegram bot token is correct
3. **Jira connection issues**: Check Jira API token and URL

### Debug Commands

```bash
# Get pod details
kubectl describe pod -l app=jira-bot

# Check logs
kubectl logs -l app=jira-bot --tail=100

# Execute shell in pod
kubectl exec -it deployment/jira-bot -- /bin/bash

# Check environment variables
kubectl exec deployment/jira-bot -- env | grep -E "(TELEGRAM|JIRA)"
```

## Cleanup

To remove the deployment:

```bash
# Delete deployment
kubectl delete -f k8s-deployment-only.yaml

# Delete secrets
kubectl delete -f k8s-secrets-prod.yaml
```

## Security Notes

- Secrets are stored in Kubernetes secrets (base64 encoded)
- Consider using external secret management (e.g., HashiCorp Vault) for production
- The service is ClusterIP type (internal access only)
- No persistent volumes are used (stateless application)
