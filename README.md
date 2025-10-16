# Jira Telegram Bot

A Telegram bot that creates Jira stories in the AAI project with the 'org' component.

## Features

- `/task <description>` - Creates a new Jira story in the AAI project
- `/help` - Shows available commands
- `/start` - Starts the bot

## Setup

### 1. Install Dependencies

#### Using uv (recommended):
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install with dev dependencies
uv sync --group dev
```

#### Using pip:
```bash
pip install -e .
```

### 2. Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Using just (recommended)
just setup

# Or manually copy the example file
cp .env.example .env
```

**Note:** The `.env` file is automatically ignored by git to protect your sensitive credentials.

Required environment variables:

- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token (get from @BotFather)
- `JIRA_USERNAME` - Your Jira username
- `JIRA_API_TOKEN` - Your Jira API token (generate from Jira profile settings)

Optional environment variables (defaults provided):

- `ALLOWED_USERS` - Comma-separated list of authorized usernames and user IDs (leave empty to allow all users)
- `JIRA_URL` - Jira server URL (default: https://myteam.aeroclub.ru)
- `JIRA_PROJECT_KEY` - Project key (default: AAI)
- `JIRA_COMPONENT_NAME` - Component name (default: org)

### 3. Getting Jira API Token

1. Go to your Jira profile settings
2. Navigate to Security → API tokens
3. Create a new API token
4. Use this token as `JIRA_API_TOKEN`

**Note:** The bot uses Bearer token authentication, which is more secure than basic auth.

### 4. Getting Telegram Bot Token

1. Message @BotFather on Telegram
2. Use `/newbot` command
3. Follow the instructions to create a new bot
4. Copy the provided token

### Quick Start:

```bash
# 1. Install just (if not already installed)
# macOS: brew install just
# Linux: curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin

# 2. Setup environment (creates .env from template)
just setup

# 3. Edit .env file with your credentials
# Required: TELEGRAM_BOT_TOKEN, JIRA_USERNAME, JIRA_API_TOKEN

# 4. Validate configuration
just validate

# 5. Build and run
just build
just run

# 6. View logs
just logs

# 7. Stop when done
just stop
```

## Running the Bot

### Local Development

#### Using uv:
```bash
uv run python main.py
```

#### Using pip:
```bash
python main.py
```

### Docker Deployment

#### Using Just (recommended):
```bash
# Install just if you haven't already
# macOS: brew install just
# Linux: curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin

# Build and run
just build
just run

# View logs
just logs

# Stop the bot
just stop

# Rebuild and restart
just rebuild
```

#### Using Docker Compose:
```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

#### Using Docker directly:
```bash
# Build the production image
docker build -t jira-bot .

# Run the container
docker run -d \
  --name jira-bot \
  --env-file .env \
  --restart unless-stopped \
  jira-bot

# View logs
docker logs -f jira-bot

# Stop the container
docker stop jira-bot
docker rm jira-bot
```

#### Development with Docker:
```bash
# Using Just
just build-dev
just dev

# Using Docker directly
docker build -f Dockerfile.dev -t jira-bot-dev .
docker run --rm -it --env-file .env --name jira-bot-dev jira-bot-dev
```

#### All Available Just Commands:
```bash
just                    # Show all available commands
just setup              # Setup environment file from template
just validate           # Validate environment variables
just start              # Full setup and run (interactive)
just build              # Build production Docker image
just build-dev          # Build development Docker image
just run                # Run with docker-compose (detached)
just run-fg             # Run with docker-compose (foreground)
just stop               # Stop the bot
just logs               # View all logs
just logs-bot           # View bot logs only
just restart            # Restart the bot
just rebuild            # Rebuild and restart
just clean              # Clean up Docker resources
just dev                # Run development container
just install            # Install dependencies locally
just local              # Run locally with uv
just status             # Check container status
just shell              # Execute shell in running container
```

#### Docker Management Commands:
```bash
# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# View container logs
docker logs <container-name>

# Execute commands in running container
docker exec -it <container-name> /bin/bash
```

## Usage

1. Start a conversation with your bot on Telegram
2. Use `/task Your task description here` to create a Jira story
3. The bot will return the created task key and URL

### Available Commands:

- `/start` - Start the bot
- `/task <description>` - Create a new Jira story (requires authorization)
- `/userinfo` - Show your user information and access status
- `/admin` - Show admin information (requires authorization)
- `/help` - Show available commands

### User Authorization:

The bot supports user authorization to restrict who can create Jira tasks:

1. **Allow all users** (default): Leave `ALLOWED_USERS` empty
2. **Restrict access**: Set `ALLOWED_USERS` with usernames and user IDs

Example configuration:
```bash
# Allow specific users
ALLOWED_USERS=john_doe,123456789,jane_smith,987654321

# Allow all users (default)
ALLOWED_USERS=
```

Example:
```
/task Implement user authentication system
```

The bot will create a Jira story with:
- Project: AAI
- Issue Type: Story
- Component: org
- Summary: Your provided description

## Troubleshooting

### Common Issues

#### Bot not responding:
1. Check if the bot is running: `docker ps`
2. View logs: `docker logs jira-bot`
3. Verify environment variables in `.env` file
4. Ensure Telegram bot token is correct

#### Jira connection issues:
1. Verify Jira URL is accessible
2. Check Jira API token (Bearer authentication)
3. Ensure the AAI project exists
4. Verify the 'org' component exists in the project

**Test your Jira token:**
```bash
curl -H "Accept: application/json" \
     -H "Authorization: Bearer YOUR_API_TOKEN" \
     "https://myteam.aeroclub.ru/rest/api/2/myself"
```

#### Docker issues:
1. **Permission denied**: Run `sudo docker` commands or add user to docker group
2. **Port conflicts**: Change ports in docker-compose.yml if needed
3. **Build failures**: Check Dockerfile syntax and dependencies

### Environment Variables Checklist:
- [ ] `TELEGRAM_BOT_TOKEN` - Valid bot token from @BotFather
- [ ] `JIRA_USERNAME` - Your Jira username
- [ ] `JIRA_API_TOKEN` - Valid API token from Jira
- [ ] `JIRA_URL` - Correct Jira server URL (default: https://myteam.aeroclub.ru)
- [ ] `JIRA_PROJECT_KEY` - Project key (default: AAI)
- [ ] `JIRA_COMPONENT_NAME` - Component name (default: org)

### Logs and Debugging:
```bash
# View real-time logs
docker-compose logs -f

# View logs from specific service
docker-compose logs -f jira-bot

# Check container status
docker-compose ps

# Restart the service
docker-compose restart jira-bot
```

## Kubernetes Deployment

### Using Helm (Recommended)

For production deployments, use Helm charts:

```bash
# Build and push image
docker build -t jira-bot:latest .
docker tag jira-bot:latest your-registry.com/jira-bot:latest
docker push your-registry.com/jira-bot:latest

# Deploy with Helm
helm install jira-bot ./helm/jira-bot -f helm/jira-bot/values-production.yaml -n jira-bot --create-namespace
```

See [HELM-DEPLOYMENT.md](HELM-DEPLOYMENT.md) for detailed Helm deployment instructions.

### Using Raw Kubernetes Manifests

For simple deployments, use raw Kubernetes manifests:

```bash
# Build and push image
docker build -t jira-bot:latest .
docker tag jira-bot:latest your-registry.com/jira-bot:latest
docker push your-registry.com/jira-bot:latest

# Deploy to Kubernetes
kubectl apply -f k8s-secrets.yaml
kubectl apply -f k8s-deployment-only.yaml
```

See [K8S-DEPLOYMENT.md](K8S-DEPLOYMENT.md) for detailed Kubernetes deployment instructions.
