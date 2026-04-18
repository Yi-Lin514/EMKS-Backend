"""
Agent 工具選擇 eval — 真 LLM 呼叫，驗證 prompt + 工具描述能引導 agent 選對工具。

設計：
- 真 LLM（跳過不會出現 stub）：沒 OPENAI_API_KEY 就 skip
- 工具本身 monkeypatch 成 spy，避免碰 DB / ChromaDB
- 每個 case 只 assert「預期工具有被呼叫」，不對其他工具做排他（條件性問題 agent 偶爾多查一個是允許的）
"""

import pytest

from app.config import settings
from app.services import agent as agent_module


pytestmark = pytest.mark.skipif(
    not settings.OPENAI_API_KEY,
    reason="OPENAI_API_KEY not set — skipping real-LLM eval",
)


@pytest.fixture
def tool_spy(monkeypatch):
    calls: list[str] = []

    def spy_factory(name: str, return_value: str):
        def _spy(*_args, **_kwargs):
            calls.append(name)
            return return_value
        return _spy

    monkeypatch.setattr(
        agent_module.search_knowledge_base, "func",
        spy_factory("search_knowledge_base",
                    "搜尋到 1 筆相關內容：\n[來源：員工請假規範，相關度：85%]\n年假每年 14 天，需提前 3 天申請。"),
    )
    monkeypatch.setattr(
        agent_module.get_recent_documents, "func",
        spy_factory("get_recent_documents",
                    "最近 7 天的文件異動共 1 筆：\n- test.pdf（v1，上傳者：Alice，更新時間：2026-04-15）"),
    )
    monkeypatch.setattr(
        agent_module.get_pending_reviews, "func",
        spy_factory("get_pending_reviews", "目前沒有待審核的文件。"),
    )
    monkeypatch.setattr(
        agent_module.get_popular_questions, "func",
        spy_factory("get_popular_questions",
                    "近 7 天熱門問題 Top 5：\n- 請假流程（3 次）\n- 報銷方式（2 次）"),
    )

    return calls


@pytest.mark.parametrize(
    "question, is_admin, expected_tool",
    [
        ("公司請假流程是什麼？", False, "search_knowledge_base"),
        ("最近一週新增了哪些文件？", False, "get_recent_documents"),
        ("目前有哪些待審核的文件？", False, "get_pending_reviews"),
        ("最近大家最常問什麼問題？", True, "get_popular_questions"),
    ],
)
def test_agent_picks_correct_tool(question, is_admin, expected_tool, tool_spy):
    agent_module.run_agent(question=question, is_admin=is_admin, user_id=1)

    assert expected_tool in tool_spy, (
        f"Agent 沒選到預期工具 `{expected_tool}`，實際呼叫：{tool_spy or '無'}"
    )
