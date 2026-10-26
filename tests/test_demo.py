import json

import server.demo as demo


def test_demo_refuses_fixture(tmp_path, monkeypatch) -> None:
    fake = tmp_path / "results.json"
    fake.write_text(json.dumps({"meta": {"fixture": True}}), encoding="utf-8")
    monkeypatch.setattr(demo, "RESULTS", fake)
    assert "fixture" in demo.check_results()


def test_demo_refuses_missing_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo, "RESULTS", tmp_path / "nope.json")
    assert "missing" in demo.check_results()


def test_demo_accepts_the_real_results() -> None:
    assert demo.check_results() is None
