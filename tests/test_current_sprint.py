"""Tests for team-aware `sprint: current` resolution.

Several teams share one Jira board, so more than one sprint is active at once
and `current` has to pick the right one. See app/teams.py.
"""

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.sprint_service import SprintService
from app.teams import team_for_sprint_name, team_for_username
from app.telegram_bot import TelegramBot

AGENT = {
    "id": 841,
    "name": "2026Q3-S3_agent",
    "state": "active",
    "startDate": "2026-08-03",
}
RECSYS = {
    "id": 842,
    "name": "2026Q3-S3_recsys",
    "state": "active",
    "startDate": "2026-08-03",
}
FOREIGN = {
    "id": 759,
    "name": "Sprint 31-33.26 Team CaT",
    "state": "active",
    "startDate": "2026-07-29",
}


@pytest.fixture(autouse=True)
def stable_config(monkeypatch):
    monkeypatch.setattr(Config, "JIRA_PROJECT_KEY", "AAI")
    monkeypatch.setattr(Config, "JIRA_COMPONENT_NAME", "org")


def _service(active=(AGENT, RECSYS, FOREIGN), current_user="Lev.Ragulin", counts=None):
    """SprintService with the Jira client stubbed out.

    `counts` maps a JQL substring to the issue count the search should report,
    so history-based guessing can be driven from a test.
    """
    jira = MagicMock()
    jira.current_user.return_value = current_user

    def search(jql, **kwargs):
        total = 0
        for needle, value in (counts or {}).items():
            if needle in jql:
                total = value
        return MagicMock(total=total)

    jira.search_issues.side_effect = search

    svc = SprintService(jira)
    svc._sprints_by_state = {"active": list(active), "future": [], "closed": []}
    svc._board_id = 326
    return svc


# --- team markers ----------------------------------------------------------


def test_team_for_sprint_name():
    assert team_for_sprint_name("2026Q3-S3_agent") == "agent"
    assert team_for_sprint_name("2025Q1S6_ai_agent") == "agent"
    assert team_for_sprint_name("2025Q3-S3/1_recsys") == "recsys"
    assert team_for_sprint_name("Sprint 31-33.26 Team CaT") is None


def test_team_for_username_is_case_insensitive():
    # Real Jira usernames are inconsistently cased.
    assert team_for_username("Lev.Ragulin") == "agent"
    assert team_for_username("danila.redikultsev") == "agent"
    assert team_for_username("DANILA.REDIKULTSEV") == "agent"
    assert team_for_username("Kirill.Fomenko") is None


# --- roster path -----------------------------------------------------------


def test_current_picks_team_sprint_by_roster_assignee():
    svc = _service(current_user="Kirill.Fomenko")
    sprint_id, message = svc.find_sprint("current", assignee="Filipp.Baranov")
    assert (sprint_id, message) == (841, None)
    assert "2026Q3-S3_agent" in svc.last_selection_note
    # Roster hits must not cost a Jira query.
    svc.jira.search_issues.assert_not_called()


def test_current_falls_back_to_the_reporters_team():
    svc = _service(current_user="Lev.Ragulin")
    sprint_id, message = svc.find_sprint("текущий")
    assert (sprint_id, message) == (841, None)
    assert "you: Lev.Ragulin" in svc.last_selection_note


def test_non_roster_assignee_without_history_goes_to_the_default_team():
    svc = _service(current_user="Lev.Ragulin", counts={})
    sprint_id, message = svc.find_sprint("current", assignee="Kirill.Fomenko")
    assert (sprint_id, message) == (842, None)
    assert "default" in svc.last_selection_note


def test_active_is_a_synonym_of_current():
    svc = _service()
    assert svc.find_sprint("active", assignee="Elena.Donskaya")[0] == 841


def test_foreign_team_sprint_is_never_picked():
    # The CaT sprint sits on our board but holds no issues of this project.
    svc = _service(active=(AGENT, RECSYS, FOREIGN))
    for username in ("Lev.Ragulin", "Kirill.Fomenko"):
        assert svc.find_sprint("current", assignee=username)[0] in (841, 842)


# --- history path ----------------------------------------------------------


def test_history_by_assignee_wins_over_the_default():
    svc = _service(
        current_user="Lev.Ragulin",
        counts={'sprint in (841) AND assignee = "Kirill.Fomenko"': 3},
    )
    sprint_id, message = svc.find_sprint("current", assignee="Kirill.Fomenko")
    assert (sprint_id, message) == (841, None)
    assert "history of assignee" in svc.last_selection_note


def test_history_by_component_used_when_assignee_is_unknown():
    svc = _service(
        current_user="Denis.Kladov",
        counts={'sprint in (842) AND component = "avia-ranker"': 12},
    )
    sprint_id, message = svc.find_sprint("current", component="avia-ranker")
    assert (sprint_id, message) == (842, None)
    assert "history of component" in svc.last_selection_note


def test_history_without_a_clear_margin_is_inconclusive():
    svc = _service(
        current_user="Denis.Kladov",
        counts={
            'sprint in (841) AND assignee = "Denis.Kladov"': 4,
            'sprint in (842) AND assignee = "Denis.Kladov"': 3,
        },
    )
    # No clear winner -> falls through to the default team.
    sprint_id, _ = svc.find_sprint("current", assignee="Denis.Kladov")
    assert sprint_id == 842
    assert "default" in svc.last_selection_note


def test_running_sprints_outweigh_a_longer_past_on_another_team():
    """Someone who just moved teams should follow their current work."""
    svc = _service(
        current_user="Lev.Ragulin",
        counts={
            # Running sprints only: all of his current work is on agent.
            'sprint in (841) AND assignee = "Denis.Kladov"': 6,
            'sprint in (842) AND assignee = "Denis.Kladov"': 0,
            # Widened to closed sprints, his recsys past would dominate.
            'sprint in (841, 659) AND assignee = "Denis.Kladov"': 7,
            'sprint in (842, 663) AND assignee = "Denis.Kladov"': 32,
        },
    )
    svc._sprints_by_state["closed"] = [
        {
            "id": 659,
            "name": "2025Q3-S3_agent",
            "state": "closed",
            "startDate": "2025-08-04",
        },
        {
            "id": 663,
            "name": "2025Q3-S2_recsys",
            "state": "closed",
            "startDate": "2025-07-21",
        },
    ]
    sprint_id, _ = svc.find_sprint("current", assignee="Denis.Kladov")
    assert sprint_id == 841


def test_explicit_component_outranks_the_reporters_team():
    svc = _service(
        current_user="Lev.Ragulin",  # roster: agent
        counts={'sprint in (842) AND component = "avia-ranker"': 12},
    )
    sprint_id, _ = svc.find_sprint("current", component="avia-ranker")
    assert sprint_id == 842


def test_unknown_teams_only_still_asks_the_user():
    svc = _service(active=(FOREIGN, dict(FOREIGN, id=760, name="Other board sprint")))
    sprint_id, message = svc.find_sprint("current")
    assert sprint_id is None
    assert "Multiple active sprints" in message


def test_other_project_does_not_get_this_projects_team_sprint():
    """The board and the rosters are AAI's; `project:` must disable guessing."""
    svc = _service(current_user="Lev.Ragulin")
    sprint_id, message = svc.find_sprint(
        "current", assignee="Filipp.Baranov", project_key="SV"
    )
    assert sprint_id is None
    assert "Multiple active sprints" in message
    assert svc.last_selection_note is None


def test_own_project_key_still_resolves():
    svc = _service(current_user="Lev.Ragulin")
    assert svc.find_sprint("current", project_key="aai")[0] == 841


def test_single_active_sprint_needs_no_team():
    svc = _service(active=(AGENT,), current_user=None)
    assert svc.find_sprint("current") == (841, None)
    assert svc.last_selection_note is None


# --- wiring through the parser --------------------------------------------


@pytest.fixture
def bot():
    b = object.__new__(TelegramBot)
    b.component_service = None
    b.sprint_service = None
    b.assignee_service = None
    b.epic_service = None
    return b


async def test_parser_resolves_assignee_before_sprint(bot, update_factory):
    """`sprint: current` must see the resolved assignee, whatever the order."""
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("Filipp.Baranov", None)
    sprint_service = _service(current_user="Kirill.Fomenko")

    result = await bot._parse_task_parameters(
        "Fix it sprint: current assignee: Филипп",
        upd,
        sprint_service=sprint_service,
        assignee_service=assignee_service,
    )

    assert result[4] == 841  # sprint_id -> the agent sprint
    assert result[7] == "Filipp.Baranov"
    assert result[9] is False
    # The auto-picked sprint is reported back to the user.
    assert any(
        "2026Q3-S3_agent" in call.args[0]
        for call in upd.message.reply_text.await_args_list
    )


async def test_parser_does_not_vote_with_the_default_component(bot, update_factory):
    """The configured default component must not be used as a team signal."""
    upd = update_factory()
    sprint_service = _service(current_user="Lev.Ragulin")
    sprint_service.find_sprint = MagicMock(return_value=(841, None))

    await bot._parse_task_parameters(
        "Fix it sprint: current", upd, sprint_service=sprint_service
    )

    assert sprint_service.find_sprint.call_args.kwargs["component"] is None
