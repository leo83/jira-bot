"""Tests for the polling watchdog, /help splitting and BadRequest handling in _with_retry."""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest, NetworkError
from telegram.ext import Application

from app.telegram_bot import TelegramBot, split_message
from app.watchdog import HeartbeatHTTPXRequest, PollingWatchdog


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_watchdog_does_not_fire_while_beating():
    clock = FakeClock()
    on_stall = MagicMock()
    wd = PollingWatchdog(timeout=300, on_stall=on_stall, clock=clock)
    for _ in range(10):
        clock.now += 60
        wd.beat()
        assert wd.check() is False
    on_stall.assert_not_called()


def test_watchdog_fires_after_timeout_without_beat():
    clock = FakeClock()
    on_stall = MagicMock()
    wd = PollingWatchdog(timeout=300, on_stall=on_stall, clock=clock)
    clock.now += 300
    assert wd.check() is False
    clock.now += 1
    assert wd.check() is True
    on_stall.assert_called_once()


def test_watchdog_thread_calls_on_stall_and_stops():
    fired = threading.Event()
    wd = PollingWatchdog(timeout=0.05, check_interval=0.01, on_stall=fired.set)
    wd.start()
    assert fired.wait(2)
    wd.stop()


def test_watchdog_stop_prevents_firing():
    on_stall = MagicMock()
    wd = PollingWatchdog(timeout=60, check_interval=0.01, on_stall=on_stall)
    wd.start()
    wd.stop()
    on_stall.assert_not_called()


async def test_heartbeat_request_beats_on_response_not_on_transport_error():
    wd = PollingWatchdog(timeout=300, on_stall=MagicMock())
    wd.beat = MagicMock()
    req = HeartbeatHTTPXRequest(wd, connection_pool_size=1)

    with patch(
        "telegram.request.HTTPXRequest.do_request",
        new=AsyncMock(return_value=(502, b"{}")),
    ):
        assert await req.do_request("https://api.telegram.org/x", "POST") == (
            502,
            b"{}",
        )
    wd.beat.assert_called_once()

    wd.beat.reset_mock()
    with patch(
        "telegram.request.HTTPXRequest.do_request",
        new=AsyncMock(side_effect=NetworkError("httpx.ConnectError")),
    ):
        with pytest.raises(NetworkError):
            await req.do_request("https://api.telegram.org/x", "POST")
    wd.beat.assert_not_called()


def test_builder_accepts_heartbeat_request_with_proxy():
    wd = PollingWatchdog(timeout=300, on_stall=MagicMock())
    app = (
        Application.builder()
        .token("123:abc")
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .proxy("http://user:pass@proxy.example:3128")
        .get_updates_request(
            HeartbeatHTTPXRequest(
                wd, connection_pool_size=1, proxy="http://proxy.example:3128"
            )
        )
        .build()
    )
    assert isinstance(app.bot._request[0], HeartbeatHTTPXRequest)


def test_split_message_respects_limit_and_keeps_text():
    paragraphs = [f"line {i} " + "x" * 50 for i in range(200)]
    text = "\n\n".join(paragraphs)
    chunks = split_message(text, limit=4000)
    assert len(chunks) > 1
    assert all(len(c) <= 4000 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_message_short_text_single_chunk():
    assert split_message("hello") == ["hello"]


def test_split_message_without_newlines_hard_cuts():
    chunks = split_message("a" * 9000, limit=4000)
    assert [len(c) for c in chunks] == [4000, 4000, 1000]


def _bot():
    return object.__new__(TelegramBot)


async def test_help_command_sends_chunks_under_telegram_limit():
    bot = _bot()
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    await bot.help_command(update, MagicMock())
    sent = [c.args[0] for c in update.message.reply_text.await_args_list]
    assert sent
    assert all(len(s) <= 4096 for s in sent)
    assert "/linkmany" in "".join(sent)


async def test_with_retry_does_not_retry_or_exit_on_bad_request():
    bot = _bot()
    handler = AsyncMock(side_effect=BadRequest("Message is too long"))
    handler.__name__ = "help_command"
    with patch("app.telegram_bot.os._exit") as exit_mock:
        await bot._with_retry(handler)(MagicMock(), MagicMock())
    assert handler.await_count == 1
    exit_mock.assert_not_called()


async def test_with_retry_exits_after_network_errors():
    bot = _bot()
    handler = AsyncMock(side_effect=NetworkError("httpx.ConnectError"))
    handler.__name__ = "task_command"
    with (
        patch("app.telegram_bot.os._exit") as exit_mock,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await bot._with_retry(handler, max_retries=2)(MagicMock(), MagicMock())
    assert handler.await_count == 2
    exit_mock.assert_called_once_with(1)


def test_watchdog_uses_busy_timeout_while_handler_runs():
    clock = FakeClock()
    on_stall = MagicMock()
    wd = PollingWatchdog(timeout=300, busy_timeout=1800, on_stall=on_stall, clock=clock)
    wd.handler_started()
    clock.now += 1000
    assert wd.check() is False
    clock.now += 801
    assert wd.check() is True
    on_stall.assert_called_once()


def test_watchdog_back_to_normal_timeout_after_handler_finishes():
    clock = FakeClock()
    on_stall = MagicMock()
    wd = PollingWatchdog(timeout=300, busy_timeout=1800, on_stall=on_stall, clock=clock)
    wd.handler_started()
    wd.handler_finished()
    wd.handler_finished()  # never goes negative
    clock.now += 301
    assert wd.check() is True


async def test_with_retry_marks_handler_busy_and_always_releases():
    bot = _bot()
    bot.watchdog = PollingWatchdog(timeout=300, on_stall=MagicMock())
    seen = []

    async def handler(update, context):
        seen.append(bot.watchdog._busy)
        raise BadRequest("Message is too long")

    await bot._with_retry(handler)(MagicMock(), MagicMock())
    assert seen == [1]
    assert bot.watchdog._busy == 0
