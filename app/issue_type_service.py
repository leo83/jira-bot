import logging
from difflib import get_close_matches

from .issue_types import issue_types

logger = logging.getLogger(__name__)


class IssueTypeService:
    """Service for issue type selection based on fuzzy matching."""

    @staticmethod
    def find_issue_type(issue_type_label: str) -> tuple[str, str]:
        """
        Find the closest issue type based on fuzzy matching.

        Args:
            issue_type_label (str): The issue type label to match

        Returns:
            tuple[str, str]: (selected_issue_type, message) where message is empty if found,
                           or contains available issue types list if not found
        """
        try:
            # Find closest match using fuzzy matching (case-insensitive)
            matches = get_close_matches(
                issue_type_label.lower(),
                [t.lower() for t in issue_types],
                n=1,
                cutoff=0.7,
            )

            if matches:
                # Find the original case version of the matched issue type
                matched_lower = matches[0]
                selected_issue_type = next(
                    (t for t in issue_types if t.lower() == matched_lower), "Story"
                )
                logger.info(
                    f"Found closest issue type: '{selected_issue_type}' for input '{issue_type_label}'"
                )
                return selected_issue_type, ""
            else:
                logger.info(f"No close match found for issue type '{issue_type_label}'")
                available_types = "\n".join(
                    [f"• {issue_type}" for issue_type in issue_types]
                )
                message = f"❌ No close match found for issue type '{issue_type_label}'\n\n📋 Available issue types:\n{available_types}"
                return "Story", message

        except Exception as e:
            logger.error(f"Error in issue type selection for '{issue_type_label}': {e}")
            available_types = "\n".join(
                [f"• {issue_type}" for issue_type in issue_types]
            )
            message = f"❌ Error processing issue type '{issue_type_label}'\n\n📋 Available issue types:\n{available_types}"
            return "Story", message

    @staticmethod
    def get_available_issue_types() -> list:
        """Get list of available issue types."""
        return issue_types.copy()
