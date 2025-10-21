import logging
from difflib import get_close_matches
from typing import Optional

from transliterate import translit

from .components import components

logger = logging.getLogger(__name__)


class ComponentService:
    """Service for component selection based on transliteration and fuzzy matching."""

    def __init__(self, jira_service=None):
        """Initialize with optional Jira service for dynamic component fetching."""
        self.jira_service = jira_service
        self._cached_components = None

    def _get_components_from_jira(self) -> list[str]:
        """Fetch components from Jira project."""
        if self._cached_components is not None:
            return self._cached_components

        if not self.jira_service:
            logger.warning("No Jira service provided, using static components")
            return components

        try:
            # Fetch components from Jira project
            jira_components = self.jira_service.jira.project_components(
                self.jira_service.project_key
            )
            component_names = [comp.name for comp in jira_components]

            # Filter out components that start with "DEPRECATED"
            filtered_components = [
                comp for comp in component_names if not comp.startswith("DEPRECATED")
            ]

            self._cached_components = filtered_components
            logger.info(
                f"Fetched {len(component_names)} components from Jira, filtered to {len(filtered_components)} active components: {filtered_components}"
            )
            return filtered_components
        except Exception as e:
            logger.error(f"Failed to fetch components from Jira: {e}")
            logger.info("Falling back to static components")
            return components

    def find_component(self, component_label: str) -> tuple[str, str]:
        """
        Find the closest component based on transliteration and fuzzy matching.

        Args:
            component_label (str): The component label to match

        Returns:
            tuple[str, str]: (selected_component, message) where message is empty if found,
                           or contains available components list if not found
        """
        try:
            # Get components from Jira or fallback to static list
            available_components_list = self._get_components_from_jira()

            # Step 1: Transliterate from Russian to Latin
            transliterated = translit(component_label, "ru", reversed=True)
            logger.info(f"Transliterated '{component_label}' to '{transliterated}'")

            # Step 2: Find closest match using fuzzy matching
            matches = get_close_matches(
                transliterated, available_components_list, n=1, cutoff=0.7
            )

            if matches:
                selected_component = matches[0]
                logger.info(
                    f"Found closest component: '{selected_component}' for input '{component_label}'"
                )
                return selected_component, ""
            else:
                logger.info(f"No close match found for '{component_label}'")
                available_components = "\n".join(
                    [f"• {comp}" for comp in available_components_list]
                )
                message = f"❌ No close match found for '{component_label}'\n\n📋 Available components:\n{available_components}"
                return "default", message

        except Exception as e:
            logger.error(f"Error in component selection for '{component_label}': {e}")
            available_components_list = self._get_components_from_jira()
            available_components = "\n".join(
                [f"• {comp}" for comp in available_components_list]
            )
            message = f"❌ Error processing component '{component_label}'\n\n📋 Available components:\n{available_components}"
            return "default", message

    def get_available_components(self) -> list:
        """Get list of available components."""
        return self._get_components_from_jira().copy()
