import logging
import os
from typing import List, Optional

from jira import JIRA
from jira.exceptions import JIRAError

from .config import Config

logger = logging.getLogger(__name__)


class JiraService:
    """Service class for Jira operations."""

    def __init__(self):
        """Initialize Jira service with configuration."""
        self.jira = None
        self.project_key = Config.JIRA_PROJECT_KEY
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

    def create_story(
        self,
        summary: str,
        description: str = None,
        component_name: str = None,
        issue_type: str = "Story",
        attachments: List[str] = None,
    ) -> Optional[str]:
        """
        Create a new Jira issue in the AAI project with specified component and type.

        Args:
            summary (str): The issue summary/title
            description (str, optional): The issue description
            component_name (str, optional): The component name (defaults to Config.JIRA_COMPONENT_NAME)
            issue_type (str, optional): The issue type (defaults to "Story")
            attachments (List[str], optional): List of file paths to attach to the issue

        Returns:
            str: The created issue key (e.g., 'AAI-123') or None if failed
        """
        try:
            # Get the project to verify it exists
            project = self.jira.project(Config.JIRA_PROJECT_KEY)
            logger.info(f"Found project: {project.name}")

            # Use provided component name or default to Config.JIRA_COMPONENT_NAME
            target_component = component_name or Config.JIRA_COMPONENT_NAME

            # Get the component ID for the target component
            components = self.jira.project_components(Config.JIRA_PROJECT_KEY)
            target_component_obj = None
            for component in components:
                if component.name == target_component:
                    target_component_obj = component
                    break

            if not target_component_obj:
                logger.error(
                    f"Component '{target_component}' not found in project {Config.JIRA_PROJECT_KEY}"
                )
                return None

            # Prepare issue data
            issue_dict = {
                "project": {"key": Config.JIRA_PROJECT_KEY},
                "summary": summary,
                "issuetype": {"name": issue_type},
                "components": [{"name": target_component}],
            }

            if description:
                issue_dict["description"] = description

            # Create the issue
            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Created issue: {new_issue.key}")

            # Add attachments if provided
            if attachments:
                try:
                    for attachment_path in attachments:
                        if os.path.exists(attachment_path):
                            with open(attachment_path, "rb") as f:
                                self.jira.add_attachment(issue=new_issue, attachment=f)
                            logger.info(f"Added attachment: {attachment_path}")
                            # Clean up temporary file
                            os.unlink(attachment_path)
                        else:
                            logger.warning(
                                f"Attachment file not found: {attachment_path}"
                            )
                except Exception as e:
                    logger.error(
                        f"Failed to add attachments to issue {new_issue.key}: {e}"
                    )

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
