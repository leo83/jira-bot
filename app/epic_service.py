"""Resolve a free-text epic query to a Jira epic key.

Strategy (per project, epics cached):
  1. Exact match on epic key (e.g. AAI-42 or 42) or epic name.
  2. Local transliteration + fuzzy scoring against the project's epics.
     - one clear winner  -> return it
     - several close ones -> ambiguous, ask the user to be specific (should_stop)
  3. No fuzzy match -> optional LLM booster, validated against the epic set.
  4. Still nothing -> not-found message with suggestions.
"""

import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from transliterate import translit

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.6
AMBIGUITY_BAND = 0.1
MAX_EPICS = 500


class EpicService:
    """Service for resolving epic queries to Jira epic keys."""

    def __init__(self, jira_service=None, llm_service=None):
        self.jira_service = jira_service
        self.llm_service = llm_service
        self._cache: dict[str, List[dict]] = {}

    def _get_epics(self, project_key: str) -> List[dict]:
        """Fetch (and cache per project) the epics of a project."""
        if project_key in self._cache:
            return self._cache[project_key]

        if not self.jira_service:
            return []

        jql = f'project = "{project_key}" AND issuetype = Epic ORDER BY updated DESC'
        try:
            issues = self.jira_service.jira.search_issues(
                jql, maxResults=MAX_EPICS, fields="summary"
            )
            epics = [{"key": i.key, "name": i.fields.summary or i.key} for i in issues]
            if not epics:
                logger.warning(f"No epics found in project {project_key}")
                return epics
            self._cache[project_key] = epics
            logger.info(f"Fetched {len(epics)} epics for project {project_key}")
            return epics
        except Exception as e:
            logger.error(f"Failed to fetch epics for project {project_key}: {e}")
            return []

    @staticmethod
    def _translit(text: str) -> str:
        try:
            return translit(text, "ru", reversed=True)
        except Exception:
            return text

    def _score(self, epic: dict, query: str) -> float:
        """Similarity between a query and an epic name."""
        q = query.lower()
        q_latin = self._translit(q)
        name = epic["name"].lower()
        name_latin = self._translit(name)

        scores = [
            SequenceMatcher(None, name, q).ratio(),
            SequenceMatcher(None, name_latin, q_latin).ratio(),
        ]

        # Word-containment: a query word fully present in the epic name.
        haystack = f"{name} {name_latin}"
        query_words = {w for w in (q.split() + q_latin.split()) if len(w) >= 3}
        base_words = [w for w in q.split() if len(w) >= 2]
        if query_words and base_words:
            contained = sum(1 for w in query_words if w in haystack)
            scores.append(min(1.0, contained / len(set(base_words))))

        return max(scores)

    def find_epic(
        self, query: str, project_key: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve a free-text epic query to an epic key.

        Returns:
            (epic_key, message). On success: (epic_key, None). On failure /
            ambiguity: (None, message) to show the user and stop creation.
        """
        query = (query or "").strip()
        if not query:
            return None, "❌ Please specify an epic name (epic:)."

        epics = self._get_epics(project_key)
        if not epics:
            return None, (
                f"❌ No epics found in project {project_key} "
                "(or they could not be fetched). Try again later or omit the epic."
            )

        # 1. Exact key match (AAI-42, or bare 42 -> PROJECT-42).
        key_query = query.upper()
        if key_query.isdigit():
            key_query = f"{project_key}-{key_query}"
        for e in epics:
            if key_query == e["key"].upper():
                return e["key"], None

        # 2. Exact name match (case-insensitive).
        ql = query.lower()
        for e in epics:
            if ql == e["name"].lower():
                return e["key"], None

        # 3. Fuzzy scoring.
        scored = sorted(
            ((e, self._score(e, query)) for e in epics),
            key=lambda x: x[1],
            reverse=True,
        )
        above = [(e, s) for e, s in scored if s >= MATCH_THRESHOLD]
        if above:
            best = above[0][1]
            close = [e for e, s in above if s >= best - AMBIGUITY_BAND]
            if len(close) == 1:
                logger.info(
                    f"Fuzzy matched epic '{close[0]['key']}' for '{query}' (score {best:.2f})"
                )
                return close[0]["key"], None
            return None, self._ambiguous_message(query, close)

        # 4. LLM booster for cases fuzzy missed.
        if self.llm_service and self.llm_service.is_configured():
            picked = self.llm_service.pick_option(
                query,
                [{"value": e["key"], "label": e["name"]} for e in epics],
                kind="Jira epic",
            )
            if picked:
                return picked, None

        # 5. Not found.
        return None, self._not_found_message(query, [e for e, _ in scored[:8]])

    @staticmethod
    def _format_epics(epics: List[dict]) -> str:
        return "\n".join(f"• {e['name']} ({e['key']})" for e in epics)

    def _ambiguous_message(self, query: str, epics: List[dict]) -> str:
        return (
            f"❓ Multiple epics match '{query}'. Please be more specific "
            f"(or use the epic key):\n{self._format_epics(epics)}"
        )

    def _not_found_message(self, query: str, suggestions: List[dict]) -> str:
        msg = f"❌ No epic found matching '{query}'."
        if suggestions:
            msg += "\n\nDid you mean:\n" + self._format_epics(suggestions)
        return msg
