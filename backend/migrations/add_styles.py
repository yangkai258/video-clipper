"""数据库迁移 - 添加切片风格表"""

import asyncio
from pathlib import Path

# 测试版数据库
DATABASE_PATH = Path(__file__).parent / "data" / "video_clipper_beta.db"


async def migrate():
    import aiosqlite

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 创建风格表
        await db.execute("""
        CREATE TABLE IF NOT EXISTS styles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            target_duration INTEGER DEFAULT 60,
            max_clips INTEGER DEFAULT 20,
            content_types TEXT DEFAULT '["金句","观点","故事"]',
            rules TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 插入默认风格
        default_styles = [
            {
                "id": "style_concise",
                "name": "简洁",
                "description": "时长短，切片数量多，适合快速传播",
                "target_duration": 45,
                "max_clips": 30,
                "content_types": '["金句","观点"]',
                "rules": '{"min_score": 70, "remove_silence": true, "fast_pace": true}',
            },
            {
                "id": "style_deep",
                "name": "深度",
                "description": "保留完整逻辑，适合深度学习",
                "target_duration": 180,
                "max_clips": 10,
                "content_types": '["完整逻辑","方法论"]',
                "rules": '{"min_score": 80, "keep_context": true, "fast_pace": false}',
            },
            {
                "id": "style_call",
                "name": "连麦精选",
                "description": "连麦互动切片，保留问答",
                "target_duration": 120,
                "max_clips": 15,
                "content_types": '["连麦互动","行业诊断"]',
                "rules": '{"keep_qa": true, "min_score": 75}',
            },
            {
                "id": "style_story",
                "name": "创业故事",
                "description": "个人经历，有情绪有启发",
                "target_duration": 90,
                "max_clips": 12,
                "content_types": '["创业故事","人生感悟"]',
                "rules": '{"keep_emotion": true, "min_score": 75}',
            },
        ]

        for style in default_styles:
            await db.execute(
                """
            INSERT OR IGNORE INTO styles (id, name, description, target_duration, max_clips, content_types, rules)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    style["id"],
                    style["name"],
                    style["description"],
                    style["target_duration"],
                    style["max_clips"],
                    style["content_types"],
                    style["rules"],
                ),
            )

        await db.commit()
        print("✅ 数据库迁移完成 - 添加切片风格表")


if __name__ == "__main__":
    asyncio.run(migrate())
