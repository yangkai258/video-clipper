"""资源库 LLM auto-tag service test (v2.2.19)

测 _keyword_fallback (无 LLM 依赖) + LLM 失败 fallback + 端点 manual retry.

LLM 调用 mock 掉 (实际跑要 OPENAI_API_KEY, CI 不可用).
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.services.library_tag_service import (
    _call_llm_for_tags,
    _keyword_fallback,
    generate_tags_for_resource,
)

# === _keyword_fallback (纯函数, 无 db/LLM 依赖) ===

def test_keyword_fallback_empty():
    """全空输入返 []"""
    assert _keyword_fallback("", "", "") == []


def test_keyword_fallback_chinese_2char():
    """中文 2-4 字词抽出 (substring 匹配, _keyword_fallback 优先 4 字 n-gram)"""
    tags = _keyword_fallback("深圳市卓宝科技集团直播", "屋面防水工程", "")
    # _keyword_fallback 优先 4 字 n-gram (n=4 优先), 所以"深圳市卓" / "屋面防水" 应该入
    # substring 检查: 至少一个 2 字关键词在任何 tag 里有交集
    all_text = "".join(tags)
    for kw in ("深圳", "卓宝", "屋面", "防水"):
        if kw not in all_text:
            pytest.fail(f"keyword {kw!r} 不在 tags {tags} 中")
    assert all(2 <= len(t) <= 4 for t in tags)


def test_keyword_fallback_no_stop_words():
    """停用词不返 (例 '我们' / '的')"""
    tags = _keyword_fallback("我们的直播", "项目", "今天的内容")
    assert "我们" not in tags
    assert "的" not in tags
    assert "今天" not in tags  # 4 字但有 2/3 抽法可能绕过, 至少主词不被淹没


def test_keyword_fallback_english():
    """英文单词小写 + 长度 >= 3"""
    tags = _keyword_fallback("Waterproof roof test", "from project a b c", "")
    # a / b / c 长度 < 3 不入
    # "from" 是停用词
    # "waterproof" / "roof" / "test" / "project" 应该入
    assert "waterproof" in tags or "roof" in tags or "test" in tags
    for t in tags:
        assert t.islower() or ord(t[0]) > 127  # 中文 or 小写英文


def test_keyword_fallback_max_5():
    """最多 5 tags"""
    tags = _keyword_fallback(
        "深圳市卓宝科技集团股份有限公司直播带货屋面防水涂料",
        "邹先华正在直播工程项目",
        "测试内容",
    )
    assert len(tags) <= 5


# === _call_llm_for_tags (mock LLM) ===

def test_llm_call_parsing_commas():
    """LLM 返逗号分隔, 解析成 list"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "防水, 屋面, 直播"
        tags = _call_llm_for_tags("屋面防水", "卓宝直播", "测试")
        assert tags == ["防水", "屋面", "直播"]


def test_llm_call_parsing_chinese_separator():
    """顿号分隔"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "防水、屋面、直播"
        tags = _call_llm_for_tags("屋面防水", "卓宝直播", "")
        assert tags == ["防水", "屋面", "直播"]


def test_llm_call_max_3_tags():
    """限 3 个"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "防水, 屋面, 直播, 涂料, 工程"
        tags = _call_llm_for_tags("屋面防水", "卓宝", "")
        assert len(tags) == 3
        assert tags == ["防水", "屋面", "直播"]


def test_llm_call_empty_input_no_call():
    """name + project_name 全空 → 不调 LLM, 返 None"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        tags = _call_llm_for_tags("", "", "")
        assert tags is None
        mock_llm.assert_not_called()


def test_llm_call_failure_returns_none():
    """LLM 抛异常 → 返 None (走 fallback)"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.side_effect = Exception("API key invalid")
        tags = _call_llm_for_tags("屋面防水", "卓宝", "")
        assert tags is None


# === generate_tags_for_resource (集成 + fallback 拼装) ===

def test_generate_tags_llm_only():
    """LLM 返 3 个 → 写 3 个, 不走 fallback"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "防水, 屋面, 直播"
        with patch("backend.services.library_tag_service.sync_get_db") as mock_db:
            # mock ResourceClip
            mock_rc = MagicMock()
            mock_rc.id = "test-uuid"
            mock_rc.name = "屋面防水"
            mock_rc.source_project_name = "卓宝直播"
            mock_rc.description = ""
            mock_rc.tags = []
            mock_db.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = mock_rc

            tags = generate_tags_for_resource("test-uuid")
            assert tags == ["防水", "屋面", "直播"]


def test_generate_tags_llm_fail_fallback():
    """LLM 失败 → 走 keyword fallback"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.side_effect = Exception("quota exceeded")
        with patch("backend.services.library_tag_service.sync_get_db") as mock_db:
            mock_rc = MagicMock()
            mock_rc.id = "test-uuid"
            mock_rc.name = "深圳市卓宝科技"
            mock_rc.source_project_name = "屋面防水工程"
            mock_rc.description = ""
            mock_rc.tags = []
            mock_db.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = mock_rc

            tags = generate_tags_for_resource("test-uuid")
            # 至少 1 个 (fallback 从中文名抽)
            assert len(tags) >= 1
            # 任何 tag 都不应该是停用词
            for t in tags:
                assert t not in {"我们", "的", "是"}


def test_generate_tags_llm_1_plus_fallback():
    """LLM 返 1 个 + fallback 补 1-2 个, 总数 >= 2"""
    with patch("backend.services.llm_service._call_llm") as mock_llm:
        mock_llm.return_value = "防水"  # 只 1 个
        with patch("backend.services.library_tag_service.sync_get_db") as mock_db:
            mock_rc = MagicMock()
            mock_rc.id = "test-uuid"
            mock_rc.name = "屋面防水工程"
            mock_rc.source_project_name = "深圳卓宝"
            mock_rc.description = "防水涂料测试"
            mock_rc.tags = []
            mock_db.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = mock_rc

            tags = generate_tags_for_resource("test-uuid")
            assert "防水" in tags
            assert len(tags) >= 2  # 至少 2 个 (LLM 1 + fallback 1)
            assert len(tags) <= 3  # 限 3


def test_generate_tags_resource_not_found():
    """resource 不存在 → 返 []"""
    with patch("backend.services.library_tag_service.sync_get_db") as mock_db:
        mock_db.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = None
        tags = generate_tags_for_resource("nonexistent-uuid")
        assert tags == []
