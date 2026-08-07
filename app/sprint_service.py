import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from jira import JIRA
from jira.exceptions import JIRAError
from transliterate import translit

from .config import Config
from .teams import (
    CURRENT_SPRINT_QUERIES,
    DEFAULT_TEAM,
    team_for_sprint_name,
    team_for_username,
)

logger = logging.getLogger(__name__)

# How many recently closed sprints per team to look back over when guessing a
# team from history. Bounded so the JQL stays small and the query stays fast.
HISTORY_SPRINT_LIMIT = 8
# A team wins the history vote only if it is at least this many times ahead of
# the runner-up; otherwise the signal is treated as inconclusive.
HISTORY_MARGIN = 2


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
        # Human-readable explanation of how a "current" sprint was picked, set
        # by _find_current_sprint so the caller can show it to the user (an
        # auto-picked sprint is otherwise invisible: sprint assignment happens
        # post-create and never fails loudly).
        self.last_selection_note: Optional[str] = None
        self._board_id: Optional[int] = None
        self._sprints_by_state: dict[str, List[dict]] = {}

    def _get_board_id(self) -> Optional[int]:
        """Get (and cache) the board ID for the project."""
        if self._board_id is None:
            boards = self.jira.boards(projectKeyOrID=self.project_key)
            if not boards:
                logger.warning(f"No boards found for project {self.project_key}")
                return None
            self._board_id = boards[0].id
            logger.info(f"Using board ID: {self._board_id}")
        return self._board_id

    def _get_sprints(self, state: str) -> List[dict]:
        """Get (and cache) the project's sprints in a given state."""
        if state in self._sprints_by_state:
            return self._sprints_by_state[state]

        sprints: List[dict] = []
        try:
            board_id = self._get_board_id()
            if board_id is not None:
                sprints = [
                    {
                        "id": s.id,
                        "name": s.name,
                        "state": s.state,
                        "startDate": getattr(s, "startDate", "") or "",
                    }
                    for s in self.jira.sprints(board_id, state=state)
                ]
        except Exception as e:
            logger.warning(f"Failed to get {state} sprints: {e}")
            return sprints

        self._sprints_by_state[state] = sprints
        return sprints

    def _get_all_sprints(self) -> List[dict]:
        """
        Get all sprints for the project.

        Returns:
            List of sprint dictionaries with id, name, and state
        """
        all_sprints = self._get_sprints("active") + self._get_sprints("future")
        logger.info(f"Found {len(all_sprints)} sprints")
        return all_sprints

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

    def find_sprint(
        self,
        sprint_query: str,
        assignee: Optional[str] = None,
        component: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Find the best matching sprint based on user query.

        Args:
            sprint_query: User's sprint search query
            assignee: Resolved Jira username of the issue's assignee, if the
                user asked for one. Used to pick a team when several sprints
                are active at once.
            component: Explicitly requested component name, if any. Same
                purpose as `assignee`; must be None when the component is only
                the configured default, or every issue would vote for the
                default component's team.
            project_key: Project the issue is being created in. Team resolution
                only knows about this service's own project, so a `project:`
                override disables it.

        Returns:
            Tuple of (sprint_id, message) where:
            - sprint_id is the matched sprint ID or None
            - message is an error/info message if sprint_id is None
        """
        self.last_selection_note = None

        if sprint_query.strip().lower() in CURRENT_SPRINT_QUERIES:
            # The board, the team rosters and the history queries are all tied
            # to self.project_key; for another project we can only fall back to
            # the pre-existing "single active sprint or ask" behaviour.
            own_project = (
                not project_key
                or project_key.upper() == (self.project_key or "").upper()
            )
            return self._find_current_sprint(
                assignee if own_project else None,
                component if own_project else None,
                resolve_team=own_project,
            )

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

    # ------------------------------------------------------------------
    # "current sprint" resolution
    # ------------------------------------------------------------------

    def _find_current_sprint(
        self,
        assignee: Optional[str],
        component: Optional[str],
        resolve_team: bool = True,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Pick the active sprint of the team this issue belongs to."""
        active_sprints = [s for s in self._get_all_sprints() if s["state"] == "active"]

        if not active_sprints:
            return (
                None,
                "❌ No active sprint found. Please specify a sprint name or leave sprint: parameter empty to add to backlog.",
            )

        if len(active_sprints) == 1:
            sprint = active_sprints[0]
            logger.info(
                f"Selected active sprint: {sprint['name']} (ID: {sprint['id']})"
            )
            return sprint["id"], None

        if not resolve_team:
            return None, self._multiple_active_message(active_sprints)

        # Group by team. Active sprints of teams we don't know about (other
        # teams sharing this board) drop out here and are never auto-picked.
        by_team: dict[str, List[dict]] = {}
        for sprint in active_sprints:
            team = team_for_sprint_name(sprint["name"])
            if team:
                by_team.setdefault(team, []).append(sprint)

        if not by_team:
            return None, self._multiple_active_message(active_sprints)

        if len(by_team) == 1:
            candidates = next(iter(by_team.values()))
            if len(candidates) == 1:
                sprint = candidates[0]
                logger.info(
                    f"Selected active sprint: {sprint['name']} (ID: {sprint['id']})"
                )
                return sprint["id"], None

        team, reason = self._guess_team(sorted(by_team), assignee, component)
        if not team:
            return None, self._multiple_active_message(
                [s for team_sprints in by_team.values() for s in team_sprints]
            )

        candidates = by_team[team]
        if len(candidates) > 1:
            return None, self._multiple_active_message(candidates)

        sprint = candidates[0]
        logger.info(
            f"Selected current sprint '{sprint['name']}' (ID: {sprint['id']}) "
            f"for team '{team}' ({reason})"
        )
        self.last_selection_note = f"🏃 Sprint: {sprint['name']} — {reason}"
        return sprint["id"], None

    @staticmethod
    def _multiple_active_message(sprints: List[dict]) -> str:
        sprint_list = "\n".join(f"• {s['name']}" for s in sprints)
        return (
            "❌ Multiple active sprints found and I could not tell which team "
            "this issue belongs to. Please specify which one:\n"
            f"{sprint_list}"
        )

    def _guess_team(
        self, teams: List[str], assignee: Optional[str], component: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Decide which of `teams` an issue belongs to.

        Returns (team, reason) where reason explains the choice to the user, or
        (None, None) when nothing at all points at a team.
        """
        # The reporter is the fallback subject: "current sprint" with no
        # assignee most naturally means "the sprint of the person asking".
        reporter = self._current_username() if not assignee else None

        # Signals about the issue itself (assignee, component) outrank the
        # reporter, which is only a "whose sprint did you probably mean" guess.
        # The roster is checked first: it is authoritative and costs no query.
        if assignee:
            team = team_for_username(assignee)
            if team and team in teams:
                return team, f"team {team} (assignee: {assignee})"
            team = self._team_by_history(
                teams, f'assignee = "{self._jql_quote(assignee)}"'
            )
            if team:
                return team, f"team {team} (history of assignee: {assignee})"

        if component:
            team = self._team_by_history(
                teams, f'component = "{self._jql_quote(component)}"'
            )
            if team:
                return team, f"team {team} (history of component: {component})"

        if reporter:
            team = team_for_username(reporter)
            if team and team in teams:
                return team, f"team {team} (you: {reporter})"
            team = self._team_by_history(
                teams, f'assignee = "{self._jql_quote(reporter)}"'
            )
            if team:
                return team, f"team {team} (your history: {reporter})"

        # Nothing matched - fall back, but only if we know who this is for.
        if (assignee or component or reporter) and DEFAULT_TEAM in teams:
            subject = assignee or component or reporter
            return DEFAULT_TEAM, f"team {DEFAULT_TEAM} (default for {subject})"

        return None, None

    def _current_username(self) -> Optional[str]:
        """Jira username of the token owner (the person creating the issue)."""
        try:
            return self.jira.current_user()
        except Exception as e:
            logger.warning(f"Failed to resolve current Jira user: {e}")
            return None

    @staticmethod
    def _jql_quote(value: str) -> str:
        """Escape a value for use inside a double-quoted JQL literal."""
        return (value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _team_sprint_ids(self, team: str, closed_depth: int) -> List[int]:
        """The team's active sprints plus its `closed_depth` latest closed ones."""
        sprints = [
            s
            for s in self._get_sprints("active")
            if team_for_sprint_name(s["name"]) == team
        ]
        if closed_depth:
            closed = [
                s
                for s in self._get_sprints("closed")
                if team_for_sprint_name(s["name"]) == team
            ]
            closed.sort(key=lambda s: s["startDate"], reverse=True)
            sprints += closed[:closed_depth]
        return [s["id"] for s in sprints]

    def _team_by_history(self, teams: List[str], clause: str) -> Optional[str]:
        """
        Count how many issues matching `clause` each team has, and return the
        clear winner (if any).

        Tried against the running sprints first: people move between teams, and
        what someone is working on right now beats where they used to sit. Only
        if that is inconclusive do we widen to recently closed sprints.
        """
        for closed_depth in (0, HISTORY_SPRINT_LIMIT):
            counts: dict[str, int] = {}
            for team in teams:
                sprint_ids = self._team_sprint_ids(team, closed_depth)
                if not sprint_ids:
                    continue
                ids = ", ".join(str(i) for i in sprint_ids)
                jql = (
                    f'project = "{self.project_key}" AND sprint in ({ids}) AND {clause}'
                )
                try:
                    counts[team] = self.jira.search_issues(
                        jql, maxResults=1, fields="key"
                    ).total
                except Exception as e:
                    logger.warning(f"Team history query failed for '{team}': {e}")
                    return None

            if not counts:
                return None

            ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
            best_team, best = ranked[0]
            runner_up = ranked[1][1] if len(ranked) > 1 else 0
            logger.info(
                f"Team counts for [{clause}] (closed_depth={closed_depth}): {counts}"
            )

            if best > 0 and best >= max(1, runner_up) * HISTORY_MARGIN:
                return best_team

        return None

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
