import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from jira import JIRA
from jira.exceptions import JIRAError
from transliterate import translit

from .config import Config

logger = logging.getLogger(__name__)


class SprintService:
    """Service for sprint matching and operations."""

    def __init__(self, jira: JIRA):
        """
        Initialize Sprint service.

        Args:
            jira: JIRA client instance
        """
        self.jira = jira
        self.project_key = Config.JIRA_PROJECT_KEY

    def _get_all_sprints(self) -> List[dict]:
        """
        Get all sprints for the project.

        Returns:
            List of sprint dictionaries with id, name, and state
        """
        try:
            # Get the board ID for the project
            boards = self.jira.boards(projectKeyOrID=self.project_key)
            if not boards:
                logger.warning(f"No boards found for project {self.project_key}")
                return []

            board_id = boards[0].id
            logger.info(f"Using board ID: {board_id}")

            # Get all sprints (active, future, and closed)
            all_sprints = []

            # Get active sprints
            try:
                active_sprints = self.jira.sprints(board_id, state="active")
                all_sprints.extend(
                    [
                        {"id": s.id, "name": s.name, "state": s.state}
                        for s in active_sprints
                    ]
                )
            except Exception as e:
                logger.warning(f"Failed to get active sprints: {e}")

            # Get future sprints
            try:
                future_sprints = self.jira.sprints(board_id, state="future")
                all_sprints.extend(
                    [
                        {"id": s.id, "name": s.name, "state": s.state}
                        for s in future_sprints
                    ]
                )
            except Exception as e:
                logger.warning(f"Failed to get future sprints: {e}")

            logger.info(f"Found {len(all_sprints)} sprints")
            return all_sprints

        except Exception as e:
            logger.error(f"Failed to get sprints: {e}")
            return []

    def _calculate_similarity(self, sprint_name: str, query: str) -> float:
        """
        Calculate similarity between sprint name and query.
        Uses transliteration and fuzzy matching.

        Args:
            sprint_name: Name of the sprint
            query: User's search query

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Normalize both strings
        sprint_lower = sprint_name.lower()
        query_lower = query.lower()

        # Also create transliterated versions
        try:
            sprint_latin = translit(sprint_lower, "ru", reversed=True)
        except:
            sprint_latin = sprint_lower  # If transliteration fails, use original

        try:
            query_latin = translit(query_lower, "ru", reversed=True)
        except:
            query_latin = query_lower  # If transliteration fails, use original

        # Calculate multiple similarity scores
        scores = []

        # Direct comparison
        direct_score = SequenceMatcher(None, sprint_lower, query_lower).ratio()
        scores.append(direct_score)

        # Transliterated comparison
        latin_score = SequenceMatcher(None, sprint_latin, query_latin).ratio()
        scores.append(latin_score)

        # Check if ALL query words are contained in sprint name (word matching)
        query_words = query_lower.split()
        query_latin_words = query_latin.split()

        # Count how many words match
        matches_lower = sum(1 for word in query_words if word in sprint_lower)
        matches_latin = sum(1 for word in query_latin_words if word in sprint_latin)

        # Calculate word match ratio (all words must match for high score)
        if query_words:
            word_match_score = max(matches_lower, matches_latin) / len(query_words)
            scores.append(word_match_score)

        # Return the maximum score
        return max(scores) if scores else 0.0

    def find_sprint(self, sprint_query: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Find the best matching sprint based on user query.

        Args:
            sprint_query: User's sprint search query

        Returns:
            Tuple of (sprint_id, message) where:
            - sprint_id is the matched sprint ID or None
            - message is an error/info message if sprint_id is None
        """
        if sprint_query.lower() in ["active", "активный", "aktive"]:
            # User wants to use the active sprint
            sprints = self._get_all_sprints()
            active_sprints = [s for s in sprints if s["state"] == "active"]

            if not active_sprints:
                return (
                    None,
                    "❌ No active sprint found. Please specify a sprint name or leave sprint: parameter empty to add to backlog.",
                )

            if len(active_sprints) > 1:
                sprint_list = "\n".join([f"• {s['name']}" for s in active_sprints])
                return (
                    None,
                    f"❌ Multiple active sprints found. Please specify which one:\n{sprint_list}",
                )

            sprint = active_sprints[0]
            logger.info(
                f"Selected active sprint: {sprint['name']} (ID: {sprint['id']})"
            )
            return sprint["id"], None

        # Get all sprints
        sprints = self._get_all_sprints()

        if not sprints:
            return None, "❌ No sprints found in the project."

        # Calculate similarity for each sprint
        sprint_scores = []
        for sprint in sprints:
            similarity = self._calculate_similarity(sprint["name"], sprint_query)
            sprint_scores.append((sprint, similarity))
            logger.info(f"Sprint '{sprint['name']}' similarity score: {similarity:.2f}")

        # Sort by similarity (highest first)
        sprint_scores.sort(key=lambda x: x[1], reverse=True)

        # Get the best matches (similarity > 0.4)
        threshold = 0.4
        best_matches = [(s, score) for s, score in sprint_scores if score >= threshold]

        if not best_matches:
            # No good matches found
            sprint_list = "\n".join(
                [f"• {s['name']}" for s in sprints[:10]]
            )  # Show first 10
            return (
                None,
                f"❌ No sprint found matching '{sprint_query}'. Available sprints:\n{sprint_list}",
            )

        # Check if we have multiple similar matches (within 0.1 of each other)
        best_score = best_matches[0][1]
        similar_matches = [s for s, score in best_matches if score >= best_score - 0.1]

        if len(similar_matches) > 1:
            # Multiple similar matches - ask user to be more specific
            sprint_list = "\n".join([f"• {s['name']}" for s in similar_matches])
            return (
                None,
                f"❌ Multiple sprints found matching '{sprint_query}'. Please be more specific:\n{sprint_list}",
            )

        # We have a clear winner
        best_sprint = best_matches[0][0]
        logger.info(
            f"Found best match: {best_sprint['name']} (score: {best_matches[0][1]:.2f})"
        )
        return best_sprint["id"], None

    def add_issue_to_sprint(self, issue_key: str, sprint_id: int) -> bool:
        """
        Add an issue to a sprint.

        Args:
            issue_key: The issue key (e.g., 'PROJ-123')
            sprint_id: The sprint ID

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Add the issue to the sprint
            self.jira.add_issues_to_sprint(sprint_id, [issue_key])
            logger.info(f"Added issue {issue_key} to sprint {sprint_id}")
            return True

        except JIRAError as e:
            logger.error(f"Failed to add issue {issue_key} to sprint {sprint_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error adding issue to sprint: {e}")
            return False
