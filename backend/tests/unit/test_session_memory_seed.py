import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

from services.ai_chat.session_memory import SessionMemory, _STORE, load_session, seed_memory_from_history


class _Msg:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def test_seed_memory_from_report_subject():
    _STORE.clear()
    seed_memory_from_history(
        "seed-test",
        [_Msg("user", "中农食迅的日报"), _Msg("assistant", "已生成日报。")],
    )
    mem = load_session("seed-test")
    assert mem.last_subject_name == "中农食迅"
    _STORE.clear()
