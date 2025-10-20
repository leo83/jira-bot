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

    def add_attachment(self, issue_key: str, attachment_path: str) -> bool:
        """
        Add an attachment to an existing Jira issue.

        Args:
            issue_key (str): The issue key (e.g., 'AAI-123')
            attachment_path (str): Path to the file to attach

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(attachment_path):
                logger.warning(f"Attachment file not found: {attachment_path}")
                return False

            # Get the issue
            issue = self.jira.issue(issue_key)

            # Add the attachment
            with open(attachment_path, "rb") as f:
                self.jira.add_attachment(issue=issue, attachment=f)
            logger.info(f"Added attachment to {issue_key}: {attachment_path}")

            # Clean up temporary file
            try:
                os.unlink(attachment_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {attachment_path}: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to add attachment to issue {issue_key}: {e}")
            return False

    def get_issue(self, issue_key: str) -> Optional[dict]:
        """
        Get details of a Jira issue.

        Args:
            issue_key (str): The issue key (e.g., 'AAI-123' or just '123' for default project)

        Returns:
            dict: Issue details including summary, description, status, attachments, etc.
                  None if issue not found or permission denied
        """
        try:
            # If only digits provided, prepend default project key
            if issue_key.isdigit():
                issue_key = f"{self.project_key}-{issue_key}"

            # Get the issue
            issue = self.jira.issue(issue_key, expand="attachment")

            # Extract relevant information
            issue_data = {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": issue.fields.description or "No description",
                "status": issue.fields.status.name,
                "issue_type": issue.fields.issuetype.name,
                "assignee": issue.fields.assignee.displayName
                if issue.fields.assignee
                else "Unassigned",
                "reporter": issue.fields.reporter.displayName
                if issue.fields.reporter
                else "Unknown",
                "created": issue.fields.created,
                "updated": issue.fields.updated,
                "attachments": [],
            }

            # Get attachments if any
            if hasattr(issue.fields, "attachment"):
                for attachment in issue.fields.attachment:
                    issue_data["attachments"].append(
                        {
                            "id": attachment.id,
                            "filename": attachment.filename,
                            "size": attachment.size,
                            "mimeType": attachment.mimeType,
                            "content_url": attachment.content,
                        }
                    )

            logger.info(
                f"Retrieved issue {issue_key} with {len(issue_data['attachments'])} attachments"
            )
            return issue_data

        except JIRAError as e:
            if e.status_code == 404:
                logger.warning(f"Issue {issue_key} not found")
            elif e.status_code == 403:
                logger.warning(f"Permission denied for issue {issue_key}")
            else:
                logger.error(f"Failed to get issue {issue_key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting issue {issue_key}: {e}")
            return None

    def download_attachment(
        self, attachment_url: str, attachment_filename: str
    ) -> Optional[str]:
        """
        Download a Jira attachment to a temporary file.

        Args:
            attachment_url (str): The URL of the attachment
            attachment_filename (str): The original filename of the attachment

        Returns:
            str: Path to the downloaded file, or None if failed
        """
        try:
            import tempfile

            import requests

            # Create custom headers for Bearer token authentication
            headers = {
                "Authorization": f"Bearer {Config.JIRA_API_TOKEN}",
            }

            # Download the attachment
            response = requests.get(attachment_url, headers=headers, stream=True)
            response.raise_for_status()

            # Save to temporary file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{attachment_filename}"
            ) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_path = temp_file.name

            logger.info(f"Downloaded attachment to {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"Failed to download attachment {attachment_filename}: {e}")
            return None

    def get_issue_url(self, issue_key: str) -> str:
        """Get the full URL for a Jira issue."""
        return f"{Config.JIRA_URL}/browse/{issue_key}"
