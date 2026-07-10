"""Resolve a free-text assignee query to a Jira username.

Strategy (per project, users cached):
  1. Exact match on username / email / display name.
  2. Local transliteration + fuzzy scoring against the assignable-user pool.
     - one clear winner  -> return it
     - several close ones -> ambiguous, ask the user to be specific (should_stop)
  3. No fuzzy match -> optional LLM booster (handles odd transliterations /
     misspellings the fuzzy scorer misses), validated against the pool.
  4. Still nothing -> not-found message with suggestions.
"""

import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from transliterate import translit

logger = logging.getLogger(__name__)

# A candidate must score at least this to be considered a match.
MATCH_THRESHOLD = 0.6
# Candidates within this band of the top score are treated as equally likely.
AMBIGUITY_BAND = 0.1


class AssigneeService:
    """Service for resolving assignee queries to Jira usernames."""

    def __init__(self, jira_service=None, llm_service=None):
        self.jira_service = jira_service
        self.llm_service = llm_service
        self._cache: dict[str, List[dict]] = {}

    def _get_assignable_users(self, project_key: str) -> List[dict]:
        """Fetch (and cache per project) the assignable users for a project."""
        if project_key in self._cache:
            return self._cache[project_key]

        if not self.jira_service:
            return []

        try:
            users = self.jira_service.jira.search_assignable_users_for_projects(
                "", project_key, maxResults=2000
            )
            result = []
            for u in users:
                # Server/DC exposes .name; Cloud exposes .accountId.
                name = getattr(u, "name", None) or getattr(u, "accountId", None)
                if not name:
                    continue
                result.append(
                    {
                        "name": name,
                        "displayName": getattr(u, "displayName", "") or name,
                        "email": getattr(u, "emailAddress", "") or "",
                    }
                )
            if not result:
                # Some Jira Server/DC versions return nothing for an empty-username
                # query (user-privacy settings). Don't cache the empty result so a
                # later call can succeed, and make the cause obvious in the logs.
                logger.warning(
                    f"search_assignable_users_for_projects('', {project_key}) returned "
                    "0 users; this Jira instance may not allow empty-query user listing"
                )
                return result

            self._cache[project_key] = result
            logger.info(
                f"Fetched {len(result)} assignable users for project {project_key}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Failed to fetch assignable users for project {project_key}: {e}"
            )
            return []

    @staticmethod
    def _translit(text: str) -> str:
        try:
            return translit(text, "ru", reversed=True)
        except Exception:
            return text

    def _score(self, user: dict, query: str) -> float:
        """Similarity between a query and a user, via display name + username."""
        q = query.lower()
        q_latin = self._translit(q)
        display = user["displayName"].lower()
        display_latin = self._translit(display)
        # username like "aleksei.dolzhenkov" -> "aleksei dolzhenkov"
        name_words = user["name"].lower().replace(".", " ").replace("_", " ")

        scores = [
            SequenceMatcher(None, display, q).ratio(),
            SequenceMatcher(None, display_latin, q_latin).ratio(),
            SequenceMatcher(None, name_words, q_latin).ratio(),
        ]

        # Word-containment: a query word fully present in display name / username.
        haystack = f"{display} {display_latin} {name_words}"
        query_words = {w for w in (q.split() + q_latin.split()) if len(w) >= 3}
        base_words = [w for w in q.split() if len(w) >= 2]
        if query_words and base_words:
            contained = sum(1 for w in query_words if w in haystack)
            scores.append(min(1.0, contained / len(set(base_words))))

        return max(scores)

    def find_assignee(
        self, query: str, project_key: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve a free-text assignee query to a username.

        Returns:
            (username, message). On success: (username, None). On failure /
            ambiguity: (None, message) where message should be shown to the user
            and creation should stop.
        """
        query = (query or "").strip()
        if not query:
            return None, "❌ Please specify who to assign the task to (assignee:)."

        users = self._get_assignable_users(project_key)
        if not users:
            return None, (
                f"❌ Could not fetch assignable users for project {project_key}. "
                "Try again later or omit the assignee."
            )

        # 1. Exact match (username / email / display name), case-insensitive.
        ql = query.lower()
        for u in users:
            if ql in (u["name"].lower(), u["email"].lower(), u["displayName"].lower()):
                return u["name"], None

        # 2. Fuzzy scoring.
        scored = sorted(
            ((u, self._score(u, query)) for u in users),
            key=lambda x: x[1],
            reverse=True,
        )
        above = [(u, s) for u, s in scored if s >= MATCH_THRESHOLD]
        if above:
            best = above[0][1]
            close = [u for u, s in above if s >= best - AMBIGUITY_BAND]
            if len(close) == 1:
                logger.info(
                    f"Fuzzy matched assignee '{close[0]['name']}' for '{query}' (score {best:.2f})"
                )
                return close[0]["name"], None
            return None, self._ambiguous_message(query, close)

        # 3. LLM booster for cases fuzzy missed (odd transliteration / typos).
        if self.llm_service and self.llm_service.is_configured():
            picked = self.llm_service.pick_username(
                query,
                [{"name": u["name"], "displayName": u["displayName"]} for u in users],
            )
            if picked:
                return picked, None

        # 4. Not found.
        return None, self._not_found_message(query, [u for u, _ in scored[:8]])

    @staticmethod
    def _format_users(users: List[dict]) -> str:
        return "\n".join(f"• {u['displayName']} ({u['name']})" for u in users)

    def _ambiguous_message(self, query: str, users: List[dict]) -> str:
        return (
            f"❓ Multiple users match '{query}'. Please be more specific "
            f"(use the username):\n{self._format_users(users)}"
        )

    def _not_found_message(self, query: str, suggestions: List[dict]) -> str:
        msg = f"❌ No assignee found matching '{query}'."
        if suggestions:
            msg += "\n\nDid you mean:\n" + self._format_users(suggestions)
        return msg
