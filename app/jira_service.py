import logging
from typing import Optional

from jira import JIRA
from jira.exceptions import JIRAError

from .config import Config

logger = logging.getLogger(__name__)


class JiraService:
    """Service class for Jira operations."""

    def __init__(self):
        """Initialize Jira service with configuration."""
        self.jira = None
        self._connect()

    def _connect(self):
        """Establish connection to Jira using Bearer token authentication."""
        try:
            # Create custom headers for Bearer token authentication
            headers = {
                "Authorization": f"Bearer {Config.JIRA_API_TOKEN}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            self.jira = JIRA(server=Config.JIRA_URL, options={"headers": headers})
            logger.info("Successfully connected to Jira with Bearer token")
        except JIRAError as e:
            logger.error(f"Failed to connect to Jira: {e}")
            raise

    def create_story(self, summary: str, description: str = None) -> Optional[str]:
        """
        Create a new Jira story in the AAI project with 'org' component.

        Args:
            summary (str): The story summary/title
            description (str, optional): The story description

        Returns:
            str: The created issue key (e.g., 'AAI-123') or None if failed
        """
        try:
            # Get the project to verify it exists
            project = self.jira.project(Config.JIRA_PROJECT_KEY)
            logger.info(f"Found project: {project.name}")

            # Get the component ID for 'org'
            components = self.jira.project_components(Config.JIRA_PROJECT_KEY)
            org_component = None
            for component in components:
                if component.name == Config.JIRA_COMPONENT_NAME:
                    org_component = component
                    break

            if not org_component:
                logger.error(
                    f"Component '{Config.JIRA_COMPONENT_NAME}' not found in project {Config.JIRA_PROJECT_KEY}"
                )
                return None

            # Prepare issue data
            issue_dict = {
                "project": {"key": Config.JIRA_PROJECT_KEY},
                "summary": summary,
                "issuetype": {"name": "Story"},
                "components": [{"name": Config.JIRA_COMPONENT_NAME}],
            }

            if description:
                issue_dict["description"] = description

            # Create the issue
            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Created issue: {new_issue.key}")

            return new_issue.key

        except JIRAError as e:
            logger.error(f"Failed to create Jira story: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Jira story: {e}")
            return None

    def get_issue_url(self, issue_key: str) -> str:
        """Get the full URL for a Jira issue."""
        return f"{Config.JIRA_URL}/browse/{issue_key}"
