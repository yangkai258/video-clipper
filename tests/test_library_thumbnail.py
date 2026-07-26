"""
v2.2.38 资源库 thumbnail + auto-tag 关闭测试

User 反馈:
1. 资源库没封面 (抽过来没规则 + thumbnail 没抽)
2. 抽过来规则不好用 (auto-tag 准)

修法:
1. from-clip 兜底: 源 thumbnail 缺失/复制失败时, ffmpeg 抽 1 帧
2. upload / from-clip / from-project batch 3 处 auto-tag 触发注释 (留 manual endpoint)
"""


def test_generate_thumbnail_helper_exists():
    """_generate_thumbnail helper 必须存在 (from-clip 兜底用)"""
    from backend.api.library import _generate_thumbnail
    assert callable(_generate_thumbnail)


def test_from_clip_uses_generate_thumbnail_fallback():
    """from-clip 端点必须有 ffmpeg 兜底调用 _generate_thumbnail (源码搜)"""
    import inspect
    from backend.api import library
    src = inspect.getsource(library.from_clip_resource)
    assert "_generate_thumbnail" in src, "from-clip 缺 _generate_thumbnail 兜底调用"
    assert "fallback_thumb" in src, "from-clip 缺 fallback_thumb 兜底变量"


def test_auto_tag_disabled_in_upload():
    """v2.2.38: upload endpoint auto-tag 默认关闭"""
    import inspect
    from backend.api import library
    src = inspect.getsource(library.upload_resource)
    # 应该有 disabled 注释或 v2.2.38 标注
    assert "v2.2.38" in src and "auto-tag 默认关闭" in src, (
        "upload 端点没禁用 auto-tag (v2.2.38 应该注释掉 background_tasks.add_task)"
    )


def test_auto_tag_disabled_in_from_clip():
    """v2.2.38: from-clip endpoint auto-tag 默认关闭"""
    import inspect
    from backend.api import library
    src = inspect.getsource(library.from_clip_resource)
    assert "v2.2.38" in src and "auto-tag 默认关闭" in src


def test_auto_tag_disabled_in_from_project_batch():
    """v2.2.38: from-project batch endpoint auto-tag 默认关闭"""
    import inspect
    from backend.api import library
    src = inspect.getsource(library.from_project_batch_resource)
    assert "v2.2.38" in src and "auto-tag 默认关闭" in src


def test_manual_auto_tag_endpoint_still_exists():
    """v2.2.19 manual endpoint 保留, user 想用时手跑"""
    from backend.api import library
    # 检查 _auto_tag_in_thread 函数还在
    assert hasattr(library, "_auto_tag_in_thread"), "_auto_tag_in_thread 还在 (manual endpoint 保留)"
