import logging
from difflib import get_close_matches

from transliterate import translit

from .components import components

logger = logging.getLogger(__name__)


class ComponentService:
    """Service for component selection based on transliteration and fuzzy matching."""

    @staticmethod
    def find_component(component_label: str) -> str:
        """
        Find the closest component based on transliteration and fuzzy matching.

        Args:
            component_label (str): The component label to match

        Returns:
            str: The closest matching component or 'org' as fallback
        """
        try:
            # Step 1: Transliterate from Russian to Latin
            transliterated = translit(component_label, "ru", reversed=True)
            logger.info(f"Transliterated '{component_label}' to '{transliterated}'")

            # Step 2: Find closest match using fuzzy matching
            matches = get_close_matches(transliterated, components, n=1, cutoff=0.7)

            if matches:
                selected_component = matches[0]
                logger.info(
                    f"Found closest component: '{selected_component}' for input '{component_label}'"
                )
                return selected_component
            else:
                logger.info(
                    f"No close match found for '{component_label}', using default 'org'"
                )
                return "org"

        except Exception as e:
            logger.error(f"Error in component selection for '{component_label}': {e}")
            return "org"

    @staticmethod
    def get_available_components() -> list:
        """Get list of available components."""
        return components.copy()
