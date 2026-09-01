"""内容去重

与历史选题比对，相似度 >70% 标记为重复。
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 去重阈值
SIMILARITY_THRESHOLD = 0.70
HISTORY_DAYS = 7


class DedupChecker:
    """选题去重器"""

    def __init__(self):
        self.output_dir = Path(__file__).parent.parent / "output"

    def filter(self, topics: list) -> list:
        """过滤重复选题

        Args:
            topics: 新选题列表

        Returns:
            去重后的选题列表
        """
        history = self._load_history()
        if not history:
            logger.info("无历史记录，跳过去重")
            return topics

        unique = []
        duplicates = []

        for topic in topics:
            is_dup = False
            for hist_topic in history:
                if self._similarity(topic.get("title", ""), hist_topic.get("title", "")) > SIMILARITY_THRESHOLD:
                    is_dup = True
                    break

            if is_dup:
                duplicates.append(topic)
            else:
                unique.append(topic)

        if duplicates:
            logger.info(f"去重: {len(duplicates)} 个重复选题被过滤")

        return unique

    def _load_history(self) -> list:
        """加载近 N 天的历史选题"""
        from datetime import datetime, timezone, timedelta

        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        history = []

        for i in range(1, HISTORY_DAYS + 1):
            date = (now - timedelta(days=i)).strftime("%Y%m%d")
            topics_file = self.output_dir / f"topics_{date}.json"
            if topics_file.exists():
                with open(topics_file, "r", encoding="utf-8") as f:
                    history.extend(json.load(f))

        return history

    def _similarity(self, text1: str, text2: str) -> float:
        """计算两个标题的相似度（基于字符重叠）

        简化实现：使用 Jaccard 相似度
        生产环境可替换为更高级的文本相似度算法
        """
        if not text1 or not text2:
            return 0.0

        set1 = set(text1)
        set2 = set(text2)
        intersection = set1 & set2
        union = set1 | set2

        return len(intersection) / len(union) if union else 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    checker = DedupChecker()
    test_topics = [{"title": "测试选题1"}, {"title": "测试选题2"}]
    result = checker.filter(test_topics)
    print(json.dumps(result, ensure_ascii=False, indent=2))
