from pathlib import Path

import pytest

from opslens.llm.base import LLMBadJSON, LLMUnavailable, ProviderConfig
from opslens.llm.cache import LLMCache
from opslens.llm.client import LLMClient, build_client, parse_json_reply
from opslens.llm.mock import MockProvider
from opslens.llm.ratelimit import RateLimiter


def mock(name: str, rpd: int = 1000, **kwargs) -> MockProvider:
    cfg = ProviderConfig(name=name, kind="mock", model=f"{name}-model", requests_per_day=rpd)
    return MockProvider(cfg, **kwargs)


def make_client(tmp_path: Path, *providers: MockProvider) -> LLMClient:
    db = tmp_path / "llm.sqlite"
    return LLMClient(list(providers), cache=LLMCache(db), limiter=RateLimiter(db, sleep_fn=lambda s: None))


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Sure! Here it is: {"a": 1} Hope this helps.', {"a": 1}),
        ("[1, 2]", [1, 2]),
    ],
)
def test_parse_json_reply(text, expected) -> None:
    assert parse_json_reply(text) == expected


def test_parse_json_reply_rejects_prose() -> None:
    with pytest.raises(LLMBadJSON):
        parse_json_reply("I cannot help with that.")


def test_pii_is_masked_before_the_provider_sees_it(tmp_path) -> None:
    provider = mock("main")
    client = make_client(tmp_path, provider)
    result = client.ask_json("t", "sys", "refund pending, call 9876543210 or a@b.com")
    sent_user_text = provider.sent[0][-1]["content"]
    assert "9876543210" not in sent_user_text and "a@b.com" not in sent_user_text
    assert "[PHONE]" in sent_user_text and "[EMAIL]" in sent_user_text
    assert result.pii_masked == {"[EMAIL]": 1, "[PHONE]": 1}


def test_second_identical_request_comes_from_cache(tmp_path) -> None:
    provider = mock("main", replies=['{"n": 1}'])
    client = make_client(tmp_path, provider)
    first = client.ask_json("t", "sys", "hello")
    second = client.ask_json("t", "sys", "hello")
    assert first.data == second.data == {"n": 1}
    assert not first.from_cache and second.from_cache
    assert len(provider.sent) == 1


def test_falls_back_when_main_provider_is_down(tmp_path) -> None:
    main = mock("main", fail_times=10)
    backup = mock("backup", replies=['{"ok": true}'])
    result = make_client(tmp_path, main, backup).ask_json("t", "sys", "hi")
    assert result.provider == "backup" and result.data == {"ok": True}


def test_broken_json_is_retried_once(tmp_path) -> None:
    provider = mock("main", replies=["not json", '{"ok": true}'])
    result = make_client(tmp_path, provider).ask_json("t", "sys", "hi")
    assert result.data == {"ok": True}
    assert len(provider.sent) == 2
    assert "not valid JSON" in provider.sent[1][-1]["content"]


def test_broken_twice_moves_to_next_provider(tmp_path) -> None:
    main = mock("main", replies=["nope", "still nope"])
    backup = mock("backup", replies=['{"ok": 1}'])
    result = make_client(tmp_path, main, backup).ask_json("t", "sys", "hi")
    assert result.provider == "backup"


def test_daily_budget_is_respected(tmp_path) -> None:
    main = mock("main", rpd=1, replies=['{"a": 1}', '{"a": 2}'])
    backup = mock("backup", replies=['{"b": 1}'])
    client = make_client(tmp_path, main, backup)
    assert client.ask_json("t", "sys", "first").provider == "main"
    assert client.ask_json("t", "sys", "second").provider == "backup"


def test_all_providers_failing_raises(tmp_path) -> None:
    client = make_client(tmp_path, mock("main", fail_times=5), mock("backup", fail_times=5))
    with pytest.raises(LLMUnavailable):
        client.ask_json("t", "sys", "hi")


def test_build_client_with_mock_from_config(tmp_path) -> None:
    client = build_client(["mock"], use_cache=False, db_path=tmp_path / "llm.sqlite")
    assert client.ask_json("t", "sys", "hi").data == {"mock": True, "chars": 2}


def test_minute_window_makes_third_call_wait(tmp_path) -> None:
    clock = {"t": 1_000_000.0}
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["t"] += seconds

    limiter = RateLimiter(tmp_path / "u.sqlite", now_fn=lambda: clock["t"], sleep_fn=fake_sleep)
    for _ in range(2):
        limiter.wait_for_slot("p", requests_per_minute=2)
        limiter.record_call("p")
        clock["t"] += 1.0
    waited = limiter.wait_for_slot("p", requests_per_minute=2)
    assert waited == pytest.approx(58.0)
    assert limiter.calls_today("p") == 2


def test_retry_after_parsing() -> None:
    from opslens.llm.client import retry_after_seconds
    assert retry_after_seconds("Please try again in 21.36s. Need more") == pytest.approx(21.36)
    assert retry_after_seconds("try again in 1m9.552s") == pytest.approx(69.552)
    assert retry_after_seconds("try again in 659.99ms") == pytest.approx(0.66, abs=0.01)
    assert retry_after_seconds("quota exceeded for today") is None


def test_short_rate_limit_waits_and_retries_same_provider(tmp_path) -> None:
    class RateLimitedOnce(MockProvider):
        def send(self, messages):
            if not self.sent:
                self.sent.append(messages)
                raise RuntimeError("429 Rate limit reached. Please try again in 2.5s.")
            return super().send(messages)

    waits: list[float] = []
    main = RateLimitedOnce(ProviderConfig(name="main", kind="mock", model="m"), replies=['{"ok": 1}'])
    client = LLMClient([main, mock("backup", replies=['{"b": 1}'])], sleep_fn=waits.append)
    result = client.ask_json("t", "sys", "hi")
    assert result.provider == "main" and waits == [3.5]
