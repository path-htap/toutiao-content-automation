"""热点分析与主题生成

调用 LLM（智谱AI GLM-4-Flash）分析热点数据，生成多角度选题。
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 默认 system prompt
ANALYSIS_PROMPT = """你是一位资深的内容策划编辑。请分析以下热点数据，为每个热点生成 2-3 个不同角度的选题。

要求:
1. 选题角度要差异化：资讯速递型 / 深度评论型 / 盘点列表型 / 故事叙事型
2. 每个选题包含: 标题、摘要(≤50字)、关键词、目标受众、文案类型、热度评分(1-10)
3. 标题要有吸引力但不过度标题党
4. 返回 JSON 格式

返回格式:
```json
[
  {
    "title": "选题标题",
    "summary": "选题摘要",
    "keywords": ["关键词1", "关键词2"],
    "audience": "目标受众",
    "style": "news|opinion|listicle|story",
    "score": 8,
    "source_hot_topic": "对应的热点标题"
  }
]
```"""


class TopicAnalyzer:
    """热点分析器 - LLM 驱动"""

    def __init__(self):
        self.tz = timezone(timedelta(hours=8))

    def analyze(self, hot_topics: dict) -> list:
        """分析热点数据，生成选题

        Args:
            hot_topics: 抓取的热点数据（含 toutiao 和 multi_platform）

        Returns:
            选题列表
        """
        from writers.article_agent import LLMClient

        # 合并所有热点
        all_topics = []
        all_topics.extend(hot_topics.get("toutiao", []))
        all_topics.extend(hot_topics.get("multi_platform", []))

        if not all_topics:
            logger.warning("无热点数据可分析")
            return []

        # 取热度最高的前 20 条（统一转 int，避免 str/int 混用导致排序失败）
        def _safe_hot_value(topic):
            val = topic.get("hot_value", 0)
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0
        all_topics.sort(key=_safe_hot_value, reverse=True)
        top_topics = all_topics[:20]

        # 构造 LLM 输入
        topics_text = json.dumps(
            [{"rank": t["rank"], "title": t["title"], "source": t["source"]}
             for t in top_topics],
            ensure_ascii=False
        )

        user_prompt = f"以下是今日热点数据:\n{topics_text}\n\n请生成选题清单。"

        # 调用 LLM
        client = LLMClient()
        try:
            response = client.chat([
                {"role": "system", "content": ANALYSIS_PROMPT},
                {"role": "user", "content": user_prompt}
            ])
            content = response.choices[0].message.content

            # 解析 JSON
            topics = self._parse_llm_response(content)
            logger.info(f"生成选题: {len(topics)} 个")
            return topics

        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return []

    def _parse_llm_response(self, content: str) -> list:
        """解析 LLM 返回的 JSON"""
        # 尝试提取 JSON 块
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end]
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("LLM 返回格式错误，无法解析 JSON")
            return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = TopicAnalyzer()
    # 测试用空数据
    test_data = {"toutiao": [], "multi_platform": []}
    topics = analyzer.analyze(test_data)
    print(json.dumps(topics, ensure_ascii=False, indent=2))
