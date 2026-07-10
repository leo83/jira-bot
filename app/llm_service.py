"""Thin OpenAI-compatible LLM client used for best-effort assignee guessing.

Deliberately minimal: no LangChain, no external framework. If the endpoint is
not configured (OPENAI_API_BASE / OPENAI_API_KEY unset) or unreachable, every
method degrades gracefully to ``None`` so callers fall back to fuzzy matching.
The call is given a short timeout so a slow endpoint can never freeze the bot.
"""

import logging
from typing import List, Optional

from .config import Config

logger = logging.getLogger(__name__)


class LLMService:
    """Best-effort wrapper around an OpenAI-compatible chat endpoint."""

    def __init__(self):
        self._client = None
        self._model = Config.OPENAI_MODEL
        self._timeout = Config.LLM_ASSIGNEE_TIMEOUT

        if not (Config.OPENAI_API_BASE and Config.OPENAI_API_KEY):
            logger.info(
                "LLM endpoint not configured; assignee guessing uses fuzzy matching only"
            )
            return

        try:
            import httpx
            from openai import OpenAI

            # verify=False: the internal endpoint uses a self-signed cert.
            http_client = httpx.Client(
                verify=False, timeout=self._timeout, trust_env=False
            )
            self._client = OpenAI(
                base_url=Config.OPENAI_API_BASE,
                api_key=Config.OPENAI_API_KEY,
                timeout=self._timeout,
                max_retries=0,
                http_client=http_client,
            )
            logger.info(
                f"LLM service initialized (model={self._model}, timeout={self._timeout}s)"
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            self._client = None

    def is_configured(self) -> bool:
        """True if an LLM endpoint is available."""
        return self._client is not None

    def pick_option(
        self, query: str, candidates: List[dict], kind: str = "item"
    ) -> Optional[str]:
        """
        Ask the LLM to pick the single best-matching option for a free-text query.

        Args:
            query: The user's free-text query (possibly Russian/partial/misspelled)
            candidates: List of {"value": <identifier>, "label": <human name>}
            kind: What is being matched (e.g. "Jira username", "Jira epic")

        Returns:
            The chosen value (guaranteed to be one of the candidate values), or
            None if the LLM is unavailable, errors, times out, or returns anything
            that isn't a known candidate.
        """
        if not self._client or not candidates:
            return None

        valid_values = {c["value"] for c in candidates}
        roster = "\n".join(f"{c['value']}\t{c.get('label', '')}" for c in candidates)
        system = (
            f"You match a query (possibly in Russian, transliterated, partial, or "
            f"misspelled) to the correct {kind} from a list. Reply with EXACTLY ONE "
            f"identifier from the list and nothing else. If no candidate clearly "
            f"matches, reply with the single word NONE."
        )
        user = (
            f"List (identifier<TAB>name):\n{roster}\n\n"
            f'Query: "{query}"\n\n'
            "Identifier:"
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=30,
                timeout=self._timeout,
            )
            content = (resp.choices[0].message.content or "").strip()
            # Model may wrap the answer; take the last whitespace-delimited token.
            answer = content.split()[-1] if content else ""
            if answer in valid_values:
                logger.info(f"LLM picked {kind} '{answer}' for query '{query}'")
                return answer
            logger.info(
                f"LLM returned no usable match for query '{query}' (raw: '{content}')"
            )
            return None
        except Exception as e:
            logger.warning(f"LLM {kind} lookup failed for '{query}': {e}")
            return None

    def pick_username(self, query: str, candidates: List[dict]) -> Optional[str]:
        """
        Pick the best-matching Jira username for a free-text assignee query.

        Args:
            query: The user's free-text assignee query (e.g. "редикюльцев")
            candidates: List of {"name": <username>, "displayName": <full name>}

        Returns:
            The chosen username, or None if unavailable / no confident match.
        """
        options = [
            {"value": c["name"], "label": c.get("displayName", "")} for c in candidates
        ]
        return self.pick_option(query, options, kind="Jira username (person name)")
