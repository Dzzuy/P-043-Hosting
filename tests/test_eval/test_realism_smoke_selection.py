"""Offline scenario selection checks for realism smoke probes."""

from eval.run_roleplay_realism_smoke import (
    RUNS,
    SCENARIO_04_ID,
    SCENARIO_04_RUNS,
    SCENARIO_ID,
    runs_for_scenario,
)


def test_realism_smoke_selects_scenario04_offline(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("offline selection must not construct a graph or model")

    monkeypatch.setattr("eval.run_roleplay_realism_smoke.RoleplayGraph", no_network)
    monkeypatch.setattr("eval.run_roleplay_realism_smoke.SharedLLMCustomerModel", no_network)
    monkeypatch.setattr("eval.run_roleplay_realism_smoke.SharedLLMTurnAnalysisModel", no_network)
    assert runs_for_scenario(SCENARIO_04_ID) is SCENARIO_04_RUNS
    assert runs_for_scenario(SCENARIO_ID) is RUNS
    assert all("chị" in turns[0] for turns in SCENARIO_04_RUNS.values())
