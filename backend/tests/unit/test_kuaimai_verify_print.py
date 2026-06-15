import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

from services import kuaimai_print as km


@pytest.mark.asyncio
async def test_verify_print_results_retries_until_ready(monkeypatch):
    calls: list[list[str]] = []

    async def fake_query(_sn: str, job_ids: list[str]) -> list[dict]:
        calls.append(list(job_ids))
        if len(calls) < 3:
            return []
        return [{"jobId": int(job_ids[0]), "code": 2000, "desc": "ok"}]

    monkeypatch.setattr(km, "query_print_results", fake_query)
    monkeypatch.setattr(km.settings, "kuaimai_verify_print_result", True)
    monkeypatch.setattr(km.asyncio, "sleep", lambda *_a, **_k: None)

    await km.verify_print_results("SN1", ["1779949835810"], max_polls=5)

    assert len(calls) == 3
    assert calls[0] == ["1779949835810"]


@pytest.mark.asyncio
async def test_verify_print_results_fails_on_non_success_code(monkeypatch):
    async def fake_query(_sn: str, job_ids: list[str]) -> list[dict]:
        return [{"jobId": job_ids[0], "code": 1001, "desc": "打印机离线"}]

    monkeypatch.setattr(km, "query_print_results", fake_query)
    monkeypatch.setattr(km.settings, "kuaimai_verify_print_result", True)
    monkeypatch.setattr(km.asyncio, "sleep", lambda *_a, **_k: None)

    with pytest.raises(km.KuaimaiPrintError, match="打印机离线"):
        await km.verify_print_results("SN1", ["job-1"], max_polls=1)


def test_normalize_job_id():
    assert km._normalize_job_id(1779949835810) == "1779949835810"
    assert km._normalize_job_id(1779949835810.0) == "1779949835810"
    assert km._normalize_job_id("1779949835810") == "1779949835810"


@pytest.mark.asyncio
async def test_verify_treats_kuaimai_2006_as_pending(monkeypatch):
    calls = 0

    async def fake_query(_sn: str, job_ids: list[str]) -> list[dict]:
        nonlocal calls
        calls += 1
        if calls < 3:
            return [
                {
                    "jobId": job_ids[0],
                    "code": 2006,
                    "desc": "未查询到打印结果,请稍后再试",
                    "result": False,
                }
            ]
        return [{"jobId": job_ids[0], "code": 2000, "desc": "打印成功", "result": True}]

    monkeypatch.setattr(km, "query_print_results", fake_query)
    monkeypatch.setattr(km.settings, "kuaimai_verify_print_result", True)
    monkeypatch.setattr(km.asyncio, "sleep", lambda *_a, **_k: None)

    await km.verify_print_results("SN1", ["job-pending"], max_polls=5)

    assert calls == 3


def test_is_pending_print_result_row():
    assert km._is_pending_print_result_row({"code": 2006, "desc": "未查询到打印结果,请稍后再试"})
    assert not km._is_pending_print_result_row({"code": 2000, "desc": "打印成功"})


def test_verify_timing_scales_with_label_count():
    few_initial, few_interval, few_polls = km._verify_timing_for_label_count(3)
    many_initial, many_interval, many_polls = km._verify_timing_for_label_count(40)

    assert many_initial > few_initial
    assert many_interval >= few_interval
    assert many_polls > few_polls
