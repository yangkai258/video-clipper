"""
v2.2.35 /parse-script endpoint + v2.2.33 视觉关键词 prompt 验证

防回归: 验证 prompt 包含"视觉关键词"指引 (跟 v2.2.33 视觉匹配 match 公式对齐),
Llm 抽的关键词应该是"画面/视觉"名词 (屋顶/瓦片) 不是"主题/概念" (防水/品质).
"""
import pytest


def test_parse_script_prompt_强调视觉关键词():
    """v2.2.33: prompt 必须含"视觉关键词"指引, 让 LLM 抽的关键词能跟 tag overlap 匹配."""
    from backend.services.mix_service import parse_script
    import inspect
    src = inspect.getsource(parse_script)
    assert "视觉关键词" in src, "parse_script prompt 漏'视觉关键词'指引, LLM 会抽主题词"
    assert "画面/视觉" in src, "prompt 漏'画面/视觉'类别示例 (屋顶/瓦片/雨)"


def test_parse_script_prompt_否定主题词():
    """v2.2.33: prompt 必须明确否定"主题/概念"词 (防水/品质/保障) — 这些词不会匹配画面."""
    from backend.services.mix_service import parse_script
    import inspect
    src = inspect.getsource(parse_script)
    # 跟视觉关键词对立面: 主题/概念/不要
    assert "主题/概念" in src or "不要" in src, "prompt 漏否定'主题/概念'词指引"


def test_parse_script_返空返_500_or_empty():
    """v2.2.35: parse_script 内部返 [] → API 返 500 (因为 segments 不能为空).
    测 parse_script 函数本身返 [] (上层 endpoint 会再 raise 500)."""
    from backend.services.mix_service import parse_script
    from unittest.mock import patch

    # mock _call_llm 在 llm_service 实际定义位置 (mix_service 内部 from import)
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "not a json"
        result = parse_script("测试脚本", target_duration=60)
    # parse_script 返 [] 当 LLM 解析失败 (内部 logger.error)
    assert result == [], "LLM 返 invalid JSON 时 parse_script 应返 []"


def test_parse_script_segments_format():
    """parse_script 返的 segments 必须 [{position, text, keywords}, ...] 格式."""
    from backend.services.mix_service import parse_script
    from unittest.mock import patch

    fake_response = """[
        {"position": 0, "text": "屋顶防水", "keywords": ["屋顶", "瓦片"]},
        {"position": 1, "text": "外墙施工", "keywords": ["外墙", "施工"]}
    ]"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = fake_response
        result = parse_script("屋顶防水很重要", target_duration=60)
    assert len(result) == 2
    assert result[0]["position"] == 0
    assert result[0]["text"] == "屋顶防水"
    assert result[0]["keywords"] == ["屋顶", "瓦片"]
    assert result[1]["keywords"] == ["外墙", "施工"]


def test_parse_script_endpoint_400_empty_text():
    """v2.2.35: API 端点拒绝空脚本."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    r = client.post("/api/v1/mix/parse-script", json={"script_text": ""})
    assert r.status_code == 400
    assert "script_text" in r.json()["detail"].lower() or "不能为空" in r.json()["detail"]


def test_parse_script_endpoint_500_when_llm_fail():
    """v2.2.35: LLM 返空时 endpoint 返 500."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from unittest.mock import patch

    with patch("backend.services.mix_service.parse_script", return_value=[]):
        client = TestClient(app)
        r = client.post("/api/v1/mix/parse-script", json={"script_text": "测试"})
    assert r.status_code == 500
    assert "空" in r.json()["detail"] or "失败" in r.json()["detail"]
