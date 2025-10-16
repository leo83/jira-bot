# Helm Deployment Guide

This guide explains how to deploy the Jira Bot using Helm charts.

## Prerequisites

- Kubernetes cluster
- Helm 3.x installed
- `kubectl` configured to access your cluster
- Docker image built and available in your registry

## Quick Start

### 1. Build and Push Docker Image

```bash
# Build the image
docker build -t jira-bot:latest .

# Tag for your registry
docker tag jira-bot:latest your-registry.com/jira-bot:latest

# Push to registry
docker push your-registry.com/jira-bot:latest
```

### 2. Create Production Values File

```bash
# Copy the production values template
cp helm/jira-bot/values-production.yaml helm/jira-bot/values-production-local.yaml

# Edit the file with your actual values
# IMPORTANT: Encode your secrets in base64
echo -n "your_telegram_bot_token" | base64
echo -n "your_jira_username" | base64
echo -n "your_jira_api_token" | base64
```

### 3. Deploy with Helm

```bash
# Add Helm repository (if using a chart repository)
helm repo add your-repo https://your-chart-repo.com
helm repo update

# Install the chart with namespace
helm install jira-bot ./helm/jira-bot -f helm/jira-bot/values-production-local.yaml -n jira-bot --create-namespace

# Or upgrade if already installed
helm upgrade jira-bot ./helm/jira-bot -f helm/jira-bot/values-production-local.yaml -n jira-bot
```

## Configuration

### Values File Structure

The Helm chart supports the following configuration options:

#### Image Configuration
```yaml
image:
  repository: your-registry.com/jira-bot
  pullPolicy: IfNotPresent
  tag: "latest"
```

#### Secrets Configuration
```yaml
secrets:
  create: true
  telegramBotToken: ""  # Base64 encoded
  jiraUsername: ""       # Base64 encoded
  jiraApiToken: ""      # Base64 encoded
```

#### Jira Configuration
```yaml
config:
  jira:
    url: "https://myteam.aeroclub.ru"
    projectKey: "AAI"
    componentName: "org"
  allowedUsers: "user1,123456,user2,789012"
```

#### Resource Limits
```yaml
resources:
  limits:
    cpu: 200m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

### Environment Variables

The chart automatically sets the following environment variables:

- `TELEGRAM_BOT_TOKEN` - From secrets
- `JIRA_USERNAME` - From secrets
- `JIRA_API_TOKEN` - From secrets
- `JIRA_URL` - From config
- `JIRA_PROJECT_KEY` - From config
- `JIRA_COMPONENT_NAME` - From config
- `ALLOWED_USERS` - From config

## Deployment Commands

### Install
```bash
# Install with default values
helm install jira-bot ./helm/jira-bot

# Install with custom values
helm install jira-bot ./helm/jira-bot -f helm/jira-bot/values-production-local.yaml

# Install with specific namespace
helm install jira-bot ./helm/jira-bot -n jira-bot --create-namespace

# Or use namespace from values file
helm install jira-bot ./helm/jira-bot -f helm/jira-bot/values-production.yaml -n $(yq eval '.namespace' helm/jira-bot/values-production.yaml) --create-namespace
```

### Upgrade
```bash
# Upgrade with new values
helm upgrade jira-bot ./helm/jira-bot -f helm/jira-bot/values-production-local.yaml

# Upgrade with specific namespace
helm upgrade jira-bot ./helm/jira-bot -n jira-bot -f helm/jira-bot/values-production-local.yaml
```

### Uninstall
```bash
# Uninstall the release
helm uninstall jira-bot

# Uninstall from specific namespace
helm uninstall jira-bot -n jira-bot
```

## Monitoring and Debugging

### Check Deployment Status
```bash
# List all releases
helm list

# Get release status
helm status jira-bot

# Get release values
helm get values jira-bot
```

### Check Pod Status
```bash
# Get pods
kubectl get pods -l app.kubernetes.io/name=jira-bot

# Get pod details
kubectl describe pod -l app.kubernetes.io/name=jira-bot

# Get logs
kubectl logs -l app.kubernetes.io/name=jira-bot
```

### Debug Commands
```bash
# Execute shell in pod
kubectl exec -it deployment/jira-bot -- /bin/bash

# Check environment variables
kubectl exec deployment/jira-bot -- env | grep -E "(TELEGRAM|JIRA)"

# Check secrets
kubectl get secrets
kubectl describe secret jira-bot-secrets
```

## Advanced Configuration

### Horizontal Pod Autoscaling
```yaml
autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```

### Ingress Configuration
```yaml
ingress:
  enabled: true
  className: "nginx"
  annotations:
    kubernetes.io/ingress.class: nginx
  hosts:
    - host: jira-bot.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: jira-bot-tls
      hosts:
        - jira-bot.example.com
```

### Service Account
```yaml
serviceAccount:
  create: true
  annotations: {}
  name: ""
```

## Security Best Practices

### 1. Use External Secret Management
Instead of storing secrets in values files, use external secret management:

```yaml
secrets:
  create: false
  existingSecret: "jira-bot-secrets"
```

### 2. Use Namespaces
Deploy in dedicated namespaces:

```bash
helm install jira-bot ./helm/jira-bot -n jira-bot --create-namespace
```

### 3. Use Image Pull Secrets
For private registries:

```yaml
imagePullSecrets:
  - name: myregistrykey
```

### 4. Resource Limits
Always set resource limits:

```yaml
resources:
  limits:
    cpu: 200m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

### 5. Istio Exclusion
The chart automatically excludes Istio sidecar injection:

```yaml
podAnnotations:
  sidecar.istio.io/inject: "false"
```

## Troubleshooting

### Common Issues

1. **Pod not starting**: Check secrets and image availability
2. **Bot not responding**: Verify Telegram bot token
3. **Jira connection failed**: Check Jira API token and URL
4. **Permission denied**: Verify user authorization settings

### Debug Steps

1. Check pod status: `kubectl get pods -l app.kubernetes.io/name=jira-bot`
2. Check logs: `kubectl logs -l app.kubernetes.io/name=jira-bot`
3. Check secrets: `kubectl get secrets`
4. Check environment variables: `kubectl exec deployment/jira-bot -- env`

### Useful Commands

```bash
# Get all resources
kubectl get all -l app.kubernetes.io/name=jira-bot

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp

# Port forward for local testing
kubectl port-forward service/jira-bot 8080:8080
```

## Cleanup

```bash
# Uninstall the release
helm uninstall jira-bot

# Delete namespace (if created)
kubectl delete namespace jira-bot

# Remove secrets (if created by chart)
kubectl delete secret jira-bot-secrets
```
