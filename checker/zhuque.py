"""AIGC 检测模块

说明：
- 朱雀 AI 检测需要通过腾讯云 EdgeOne 网关调用，配置较复杂。
- 默认使用本地模式检测（基于 AI 写作模式匹配），配合去 AI 味重写循环使用。
- 如需接入朱雀 API，请在腾讯云 EdgeOne 控制台创建网关后配置 ZHUQUE_API_BASE_URL。
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 阈值
DEFAULT_THRESHOLD = 25  # 本地模式：AI 模式分 ≤ 25 分视为通过（越低越好）
MAX_RETRIES = 5  # 检测-重写循环最多 5 次


class AIGCChecker:
    """AIGC 检测器（本地模式为主，朱雀 API 可选）"""

    def __init__(self):
        self.api_key = os.getenv("ZHUQUE_API_KEY", "")
        self.api_base = os.getenv("ZHUQUE_API_BASE_URL", "")
        self.tz = timezone(timedelta(hours=8))
        self.threshold = float(os.getenv("AIGC_THRESHOLD", DEFAULT_THRESHOLD))
        self.use_remote = bool(self.api_key and self.api_base)
        self.mode = "朱雀API" if self.use_remote else "本地模式检测"

        logger.info(f"AIGC检测模式: {self.mode}")
        logger.info(f"通过阈值: ≤ {self.threshold}")

    def check_articles(self, articles: list) -> dict:
        """检测多篇文章（含检测-重写循环）

        未通过的文章会自动重写并再次检测，直到通过或达到最大次数。
        重写后的内容会直接更新到 article 字典中。
        """
        from humanizer.patterns import PatternDetector

        detector = PatternDetector()
        results = []
        passed = 0
        failed = 0

        for article in articles:
            title = article.get("main_title", "")
            result = self._check_one(article, detector)
            results.append(result)

            if result.get("passed"):
                passed += 1
            else:
                failed += 1

        report = {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed}/{len(results)}" if results else "0/0",
            "results": results,
            "mode": self.mode,
            "threshold": self.threshold,
            "checked_at": datetime.now(self.tz).isoformat(),
        }

        logger.info(f"检测完成: {passed}/{len(results)} 通过 (模式: {self.mode}, 阈值: {self.threshold})")
        return report

    def _check_one(self, article: dict, detector) -> dict:
        """检测单篇文章（含检测-重写循环）

        未通过则调用 Humanizer 深度重写，再检测，最多 MAX_RETRIES 次。
        """
        from humanizer.rewrite import Humanizer

        humanizer = Humanizer()
        title = article.get("main_title", "")
        retry_count = 0
        ai_score = 100.0

        while retry_count < MAX_RETRIES:
            # 检测
            current_content = article.get("content", "")

            if self.use_remote:
                ai_score = self._call_zhuque_api(current_content)
                if ai_score is None:
                    logger.warning(f"朱雀API调用失败，降级到本地模式")
                    self.use_remote = False
                    self.mode = "本地模式检测"
                    report = detector.detect(current_content)
                    ai_score = report["ai_score"]
            else:
                report = detector.detect(current_content)
                ai_score = report["ai_score"]

            logger.info(f"检测 [{title[:20]}]: AI分 {ai_score:.0f} (第{retry_count+1}次)")

            if ai_score <= self.threshold:
                logger.info(f"✅ 通过检测 [{title[:20]}]")
                return {
                    "title": title,
                    "ai_score": ai_score,
                    "passed": True,
                    "retry_count": retry_count,
                    "mode": self.mode,
                }

            # 未通过，深度重写
            retry_count += 1
            if retry_count < MAX_RETRIES:
                logger.info(f"❌ 未通过，第 {retry_count} 次深度重写...")
                temp_article = {"main_title": title, "content": current_content}
                result = humanizer._process_one(temp_article)
                article["content"] = result["content"]
                time.sleep(0.5)

        return {
            "title": title,
            "ai_score": ai_score,
            "passed": False,
            "retry_count": retry_count,
            "mode": self.mode,
        }

    def _call_zhuque_api(self, content: str) -> float:
        """调用朱雀检测 API（需配置 ZHUQUE_API_BASE_URL）

        朱雀 API 需要通过腾讯云 EdgeOne 网关调用，
        请在 EdgeOne 控制台创建网关后配置 ZHUQUE_API_BASE_URL。
        """
        if not self.api_key or not self.api_base:
            return None

        try:
            url = f"{self.api_base.rstrip('/')}/v1/detect"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = {"text": content[:5000]}

            resp = requests.post(url, headers=headers, json=data, timeout=30)

            if resp.status_code == 429:
                logger.warning("朱雀 API 限流")
                return None

            resp.raise_for_status()
            result = resp.json()

            # 解析 AI 概率
            ai_prob = result.get("data", {}).get("ai_probability", None)
            if ai_prob is not None:
                # 转换为 0-100 分制
                return float(ai_prob) * 100
            return None

        except Exception as e:
            logger.error(f"朱雀 API 调用失败: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    checker = AIGCChecker()
    test_articles = [{"main_title": "测试", "content": "这是一段测试文本。"}]
    report = checker.check_articles(test_articles)
    print(json.dumps(report, ensure_ascii=False, indent=2))
