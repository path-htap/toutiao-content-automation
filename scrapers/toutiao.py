"""今日头条热榜抓取

从今日头条获取热榜数据，结构化存储。

数据字段: 排名 / 标题 / 热度值 / 来源 / 时间戳 / URL
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

# 今日头条热榜 API
TOUTIAO_HOT_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.toutiao.com/",
}


class ToutiaoScraper:
    """今日头条热榜抓取器"""

    def __init__(self, limit: int = 50):
        self.limit = limit
        self.tz = timezone(timedelta(hours=8))

    def fetch(self) -> list:
        """抓取今日头条热榜

        Returns:
            热榜列表，每项含: rank, title, hot_value, source, timestamp, url
        """
        logger.info(f"开始抓取今日头条热榜 (limit={self.limit})")

        try:
            resp = requests.get(TOUTIAO_HOT_URL, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            items = []
            board = data.get("data", [])

            for i, item in enumerate(board[:self.limit]):
                items.append({
                    "rank": i + 1,
                    "title": item.get("Title", ""),
                    "hot_value": item.get("HotValue", 0),
                    "source": "今日头条",
                    "timestamp": datetime.now(self.tz).isoformat(),
                    "url": item.get("Url", ""),
                    "cluster_id": item.get("ClusterId", ""),
                })

            logger.info(f"抓取成功: {len(items)} 条")
            return items

        except requests.RequestException as e:
            logger.error(f"抓取失败: {e}")
            return []

    def fetch_with_retry(self, max_retries: int = 3) -> list:
        """带重试的抓取"""
        for attempt in range(max_retries):
            result = self.fetch()
            if result:
                return result
            logger.warning(f"第 {attempt + 1} 次抓取失败，重试中...")
            time.sleep(2 ** attempt)

        logger.error(f"抓取失败，已重试 {max_retries} 次")
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = ToutiaoScraper(limit=20)
    data = scraper.fetch()
    print(json.dumps(data[:3], ensure_ascii=False, indent=2))
