# Justfile for Jira Telegram Bot

# Default recipe - show help
default:
    @just --list

# Setup environment file from template
setup:
    @if [ ! -f .env ]; then \
        echo "Creating .env file from template..."; \
        cp .env.example .env; \
        echo "✅ .env file created! Please edit it with your credentials."; \
        echo "Required variables:"; \
        echo "  - TELEGRAM_BOT_TOKEN (get from @BotFather)"; \
        echo "  - JIRA_USERNAME (your Jira username)"; \
        echo "  - JIRA_API_TOKEN (generate from Jira profile)"; \
    else \
        echo "✅ .env file already exists!"; \
    fi

# Validate environment variables
validate:
    @echo "Checking environment variables..."
    @if [ ! -f .env ]; then \
        echo "❌ .env file not found. Run 'just setup' first."; \
        exit 1; \
    fi
    @if ! grep -q "your_telegram_bot_token_here" .env; then \
        echo "✅ TELEGRAM_BOT_TOKEN is set"; \
    else \
        echo "❌ TELEGRAM_BOT_TOKEN needs to be configured"; \
    fi
    @if ! grep -q "your_jira_username" .env; then \
        echo "✅ JIRA_USERNAME is set"; \
    else \
        echo "❌ JIRA_USERNAME needs to be configured"; \
    fi
    @if ! grep -q "your_jira_api_token" .env; then \
        echo "✅ JIRA_API_TOKEN is set"; \
    else \
        echo "❌ JIRA_API_TOKEN needs to be configured"; \
    fi

# Build the production Docker image (linux/amd64 for Kubernetes)
# Version is incremented from registry tags. Use: just docker-build (prod) or just docker-build .rc (RC)
docker-build extra="":
    #!/usr/bin/env bash
    if [ "{{extra}}" = ".rc" ]; then
        TAG_FULL=$(uv run python scripts/next_rc_version.py)
    else
        TAG_FULL=$(uv run python scripts/next_rc_version.py --prod)
    fi
    echo Build image with tag $TAG_FULL
    docker build --platform linux/amd64 -t proget.aeroclub.ru/aeroclub-infrastructure/library/services-ai-jira-bot:$TAG_FULL .
    docker push proget.aeroclub.ru/aeroclub-infrastructure/library/services-ai-jira-bot:$TAG_FULL

# Run the bot with docker-compose
run:
    just validate
    docker-compose up -d

# Run the bot in foreground (for debugging)
run-fg:
    just validate
    docker-compose up

# Stop the bot
stop:
    docker-compose down

# View logs
logs:
    docker-compose logs -f

# View logs for specific service
logs-bot:
    docker-compose logs -f jira-bot

# Restart the bot
restart:
    docker-compose restart jira-bot

# Rebuild and restart
rebuild:
    just validate
    docker-compose up -d --build

# Clean up Docker resources
clean:
    docker-compose down --volumes --remove-orphans
    docker system prune -f

# Run development container
dev:
    just validate
    docker run --rm -it --env-file .env --name jira-bot-dev jira-bot-dev

# Install dependencies locally
install:
    uv sync

# Run locally
local:
    just validate
    just kill-bot
    uv run python main.py

# Kill any running bot instances
kill-bot:
    @echo "Stopping any running bot instances..."
    @pkill -f "python.*main.py" || true
    @pkill -f "uv run python main.py" || true
    @echo "✅ Bot instances stopped"

# Check container status
status:
    docker-compose ps

# Check for running bot instances
check-bot:
    @echo "Checking for running bot instances..."
    @ps aux | grep -E "(python.*main\.py|uv run python main\.py)" | grep -v grep || echo "No bot instances running"

# Execute shell in running container
shell:
    docker-compose exec jira-bot /bin/bash

# Full setup and run
start:
    just setup
    @echo "Please edit .env file with your credentials, then run 'just run'"

# Deploy/upgrade Helm release with values-production
helm-deploy:
    helm upgrade --install jira-bot ./helm/jira-bot -f helm/jira-bot/values-production.yaml -n production

# Uninstall Helm release
helm-uninstall:
    helm uninstall jira-bot -n production
