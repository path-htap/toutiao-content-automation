"""多平台热搜聚合

从百度、微博、知乎等多个平台抓取热搜数据。
参考: TrendRadar / newsnow 项目逻辑
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 完整浏览器 headers（防止被反爬拦截）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# 各平台 API 配置（含备用 API）
PLATFORM_CONFIG = {
    "baidu": {
        "name": "百度热搜",
        "url": "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        "headers_extra": {"Referer": "https://top.baidu.com/board?tab=realtime"},
        "parser": "_parse_baidu",
    },
    "weibo": {
        "name": "微博热搜",
        # 移动端 API 更容易访问
        "url": "https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot",
        "headers_extra": {
            "Referer": "https://m.weibo.cn/",
            "X-Requested-With": "XMLHttpRequest",
        },
        "parser": "_parse_weibo_mobile",
    },
    "zhihu": {
        "name": "知乎热榜",
        "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50",
        "headers_extra": {
            "Referer": "https://www.zhihu.com/hot",
            "x-requested-with": "fetch",
        },
        "parser": "_parse_zhihu",
    },
    # 备用：第三方聚合 API
    "vvhan_baidu": {
        "name": "百度热搜(备用)",
        "url": "https://api.vvhan.com/api/hotlist/baiduRY",
        "headers_extra": {},
        "parser": "_parse_vvhan",
    },
    "vvhan_weibo": {
        "name": "微博热搜(备用)",
        "url": "https://api.vvhan.com/api/hotlist/wbHot",
        "headers_extra": {},
        "parser": "_parse_vvhan",
    },
    "vvhan_zhihu": {
        "name": "知乎热榜(备用)",
        "url": "https://api.vvhan.com/api/hotlist/zhihuHot",
        "headers_extra": {},
        "parser": "_parse_vvhan",
    },
}


class MultiPlatformScraper:
    """多平台热搜聚合抓取器

    策略：先尝试官方 API，失败后自动切换备用 API
    """

    def __init__(self):
        self.tz = timezone(timedelta(hours=8))
        self._load_config()

    def _load_config(self):
        """从 sources.json 加载平台配置"""
        config_path = Path(__file__).parent.parent / "config" / "sources.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def fetch(self) -> list:
        """抓取所有启用的平台热搜

        Returns:
            聚合热搜列表
        """
        all_items = []
        # 每个平台只抓一次（优先官方，失败用备用）
        platforms_done = set()

        for key, platform_cfg in PLATFORM_CONFIG.items():
            platform_base = key.split("_")[0]  # baidu / weibo / zhihu
            if platform_base in platforms_done:
                continue

            source_config = self.config.get(platform_base, {})
            if not source_config.get("enabled", True):
                logger.info(f"平台 {platform_cfg['name']} 已禁用，跳过")
                platforms_done.add(platform_base)
                continue

            limit = source_config.get("limit", 30)
            items = self._fetch_platform(key, limit)

            if items:
                all_items.extend(items)
                platforms_done.add(platform_base)
            else:
                # 官方 API 失败，尝试备用
                backup_key = f"vvhan_{platform_base}"
                if backup_key in PLATFORM_CONFIG and backup_key not in platforms_done:
                    logger.info(f"{platform_base} 官方 API 失败，尝试备用 API")
                    items = self._fetch_platform(backup_key, limit)
                    if items:
                        all_items.extend(items)
                        platforms_done.add(platform_base)

            time.sleep(0.5)  # 礼貌延迟

        logger.info(f"多平台聚合: 共 {len(all_items)} 条")
        return all_items

    def _fetch_platform(self, platform: str, limit: int) -> list:
        """抓取单个平台"""
        cfg = PLATFORM_CONFIG[platform]
        name = cfg["name"]
        url = cfg["url"]

        try:
            headers = {**HEADERS, **cfg.get("headers_extra", {})}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            parser = getattr(self, cfg["parser"])
            items = parser(data, name, limit)
            logger.info(f"{name}: {len(items)} 条")
            return items

        except Exception as e:
            logger.warning(f"{name} 抓取失败: {e}")
            return []

    def _parse_baidu(self, data: dict, name: str, limit: int) -> list:
        """解析百度热搜"""
        items = []
        try:
            cards = data.get("data", {}).get("cards", [])
            if cards:
                board = cards[0].get("content", [])
            else:
                board = data.get("data", {}).get("content", [])

            for i, item in enumerate(board[:limit]):
                items.append({
                    "rank": i + 1,
                    "title": item.get("word", item.get("query", "")),
                    "hot_value": item.get("hotScore", item.get("hot", 0)),
                    "source": name,
                    "timestamp": datetime.now(self.tz).isoformat(),
                    "url": item.get("url", item.get("rawUrl", "")),
                })
        except Exception as e:
            logger.error(f"百度热搜解析失败: {e}")
        return items

    def _parse_weibo_mobile(self, data: dict, name: str, limit: int) -> list:
        """解析微博热搜（移动端 API）"""
        items = []
        try:
            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                if card.get("card_group"):
                    for i, item in enumerate(card["card_group"][:limit]):
                        items.append({
                            "rank": i + 1,
                            "title": item.get("desc", item.get("desc_extr", "")),
                            "hot_value": item.get("desc_extr", "0"),
                            "source": name,
                            "timestamp": datetime.now(self.tz).isoformat(),
                            "url": item.get("scheme", ""),
                        })
                        if len(items) >= limit:
                            break
                if len(items) >= limit:
                    break
        except Exception as e:
            logger.error(f"微博热搜解析失败: {e}")
        return items

    def _parse_zhihu(self, data: dict, name: str, limit: int) -> list:
        """解析知乎热榜"""
        items = []
        try:
            board = data.get("data", [])
            for i, item in enumerate(board[:limit]):
                target = item.get("target", {})
                items.append({
                    "rank": i + 1,
                    "title": target.get("title", ""),
                    "hot_value": item.get("detail_text", "0"),
                    "source": name,
                    "timestamp": datetime.now(self.tz).isoformat(),
                    "url": target.get("url", "").replace("api.zhihu.com", "www.zhihu.com"),
                })
        except Exception as e:
            logger.error(f"知乎热榜解析失败: {e}")
        return items

    def _parse_vvhan(self, data: dict, name: str, limit: int) -> list:
        """解析 vvhan 第三方聚合 API"""
        items = []
        try:
            board = data.get("data", [])
            for i, item in enumerate(board[:limit]):
                items.append({
                    "rank": i + 1,
                    "title": item.get("name", item.get("title", "")),
                    "hot_value": item.get("hot", "0"),
                    "source": name,
                    "timestamp": datetime.now(self.tz).isoformat(),
                    "url": item.get("url", item.get("mobil_url", "")),
                })
        except Exception as e:
            logger.error(f"vvhan API 解析失败: {e}")
        return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    scraper = MultiPlatformScraper()
    data = scraper.fetch()
    print(f"\n总计: {len(data)} 条")
    # 按平台分组统计
    platforms = {}
    for item in data:
        platforms[item["source"]] = platforms.get(item["source"], 0) + 1
    for p, c in platforms.items():
        print(f"  {p}: {c} 条")
    if data:
        print(json.dumps(data[:2], ensure_ascii=False, indent=2))
