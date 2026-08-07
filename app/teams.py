"""Team routing for the "current sprint" shortcut.

Several teams share one Jira board, so more than one sprint is active at any
moment (e.g. ``2026Q3-S3_agent`` and ``2026Q3-S3_recsys``). When a user writes
``sprint: current`` we have to decide *whose* current sprint they mean.

``SprintService._find_current_sprint`` resolves it in this order:

1. ``TEAM_ROSTER`` - the explicit membership list below. Costs no Jira calls,
   so the common case stays as fast as it is today.
2. History - which team's sprints this assignee / component usually lands in
   (one cheap count query per candidate team).
3. ``DEFAULT_TEAM``.

Usernames are the Jira Server ``name`` field, lowercased for lookup: the real
ones are inconsistently cased (``Lev.Ragulin`` but ``nikita.korolev``).
Verified against ``search_assignable_users_for_projects("", "AAI")``.
"""

# Jira username (lowercase) -> team key.
TEAM_ROSTER = {
    "lev.ragulin": "agent",
    "elena.donskaya": "agent",
    "anastasiya.kudinova": "agent",
    "aleksey.dolzhenkov": "agent",
    "filipp.baranov": "agent",
    "vasily.soldatkin": "agent",
    "danila.redikultsev": "agent",
    "aleksandr.avdeenko": "agent",
    "nikita.korolev": "agent",
    "vladimir.puchnin": "agent",
}

# Team key -> substrings that identify the team inside a sprint name.
# A sprint matching none of these (another team sharing the board) is never
# picked automatically; a sprint matching several is treated as unidentifiable.
TEAM_SPRINT_MARKERS = {
    "agent": ("agent",),
    "recsys": ("recsys",),
}

# Where people who are on no roster and have no usable history go.
DEFAULT_TEAM = "recsys"

# Sprint queries that mean "my team's currently running sprint".
CURRENT_SPRINT_QUERIES = {
    "active",
    "aktive",
    "активный",
    "активная",
    "current",
    "текущий",
    "текущая",
    "тек",
}


def team_for_sprint_name(sprint_name: str) -> str | None:
    """Return the team key a sprint name belongs to, or None if unidentifiable."""
    name = (sprint_name or "").lower()
    matched = {
        team
        for team, markers in TEAM_SPRINT_MARKERS.items()
        if any(marker in name for marker in markers)
    }
    return matched.pop() if len(matched) == 1 else None


def team_for_username(username: str) -> str | None:
    """Return the roster team for a Jira username, or None if not on a roster."""
    return TEAM_ROSTER.get((username or "").strip().lower())
