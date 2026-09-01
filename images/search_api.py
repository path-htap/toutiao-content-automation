"""图片搜索模块

集成 Pexels 和 Unsplash API，按关键词搜索免费商用图片。
支持限流和缓存。
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# API 配置
PEXELS_API = "https://api.pexels.com/v1/search"
UNSPLASH_API = "https://api.unsplash.com/search/photos"

# 限流（每分钟）
PEXELS_RATE_LIMIT = 200  # 每小时 200 次
UNSPLASH_RATE_LIMIT = 50  # 每小时 50 次


class ImageSearcher:
    """图片搜索器"""

    def __init__(self):
        self.pexels_key = os.getenv("PEXELS_API_KEY", "")
        self.unsplash_key = os.getenv("UNSPLASH_API_KEY", "")
        self.cache_dir = Path(__file__).parent.parent / "output" / "image_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._pexels_count = 0
        self._unsplash_count = 0
        self._cache = {}

    def search(self, keywords: str, per_page: int = 5) -> list:
        """搜索图片

        Args:
            keywords: 搜索关键词
            per_page: 每页数量

        Returns:
            图片列表: [{url, width, height, alt, source, license}]
        """
        # 检查缓存
        cache_key = keywords.lower().replace(" ", "_")
        if cache_key in self._cache:
            logger.info(f"图片缓存命中: {keywords}")
            return self._cache[cache_key]

        results = []

        # Pexels 优先
        if self._pexels_count < PEXELS_RATE_LIMIT:
            pexels_results = self._search_pexels(keywords, per_page)
            results.extend(pexels_results)

        # Unsplash 补充
        if len(results) < per_page and self._unsplash_count < UNSPLASH_RATE_LIMIT:
            remaining = per_page - len(results)
            unsplash_results = self._search_unsplash(keywords, remaining)
            results.extend(unsplash_results)

        # 缓存
        self._cache[cache_key] = results
        self._save_cache(cache_key, results)

        logger.info(f"图片搜索 '{keywords}': {len(results)} 张")
        return results

    def _search_pexels(self, keywords: str, per_page: int) -> list:
        """Pexels API 搜索"""
        if not self.pexels_key:
            return []

        try:
            headers = {"Authorization": self.pexels_key}
            params = {"query": keywords, "per_page": per_page, "locale": "zh-CN"}

            resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=10)
            self._pexels_count += 1

            if resp.status_code == 429:
                logger.warning("Pexels 限流，切换 Unsplash")
                return []

            resp.raise_for_status()
            data = resp.json()

            photos = []
            for photo in data.get("photos", []):
                photos.append({
                    "url": photo.get("src", {}).get("large", ""),
                    "thumb_url": photo.get("src", {}).get("medium", ""),
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "alt": photo.get("alt", keywords),
                    "source": "Pexels",
                    "license": "Free for commercial use",
                    "photographer": photo.get("photographer", ""),
                })

            return photos

        except Exception as e:
            logger.error(f"Pexels 搜索失败: {e}")
            return []

    def _search_unsplash(self, keywords: str, per_page: int) -> list:
        """Unsplash API 搜索"""
        if not self.unsplash_key:
            return []

        try:
            headers = {"Authorization": f"Client-ID {self.unsplash_key}"}
            params = {"query": keywords, "per_page": per_page}

            resp = requests.get(UNSPLASH_API, headers=headers, params=params, timeout=10)
            self._unsplash_count += 1

            if resp.status_code == 429:
                logger.warning("Unsplash 限流")
                return []

            resp.raise_for_status()
            data = resp.json()

            photos = []
            for photo in data.get("results", []):
                photos.append({
                    "url": photo.get("urls", {}).get("regular", ""),
                    "thumb_url": photo.get("urls", {}).get("small", ""),
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "alt": photo.get("alt_description", keywords),
                    "source": "Unsplash",
                    "license": "Free for commercial use",
                    "photographer": photo.get("user", {}).get("name", ""),
                })

            return photos

        except Exception as e:
            logger.error(f"Unsplash 搜索失败: {e}")
            return []

    def _save_cache(self, key: str, data: list):
        """保存缓存到文件"""
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    searcher = ImageSearcher()
    results = searcher.search("科技 人工智能", per_page=3)
    print(json.dumps(results[:2], ensure_ascii=False, indent=2))
