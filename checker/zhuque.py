"""朱雀 AI AIGC 检测模块

调用朱雀 AI（腾讯）检测 API，判断文本是否为 AI 生成。
每日免费 20 次，需做额度管理。
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 朱雀检测 API
ZHUQUE_API = "https://matrix.tencent.com/api/ai-detect/v1/detect"

# 阈值
DEFAULT_THRESHOLD = 0.30  # AI 概率 ≤ 30% 视为通过
MAX_RETRIES = 3  # 检测-重写循环最多 3 次
DAILY_LIMIT = 20  # 每日 20 次免费额度


class ZhuqueChecker:
    """朱雀 AI 检测器"""

    def __init__(self):
        self.api_key = os.getenv("ZHUQUE_API_KEY", "")
        self.tz = timezone(timedelta(hours=8))
        self.threshold = float(os.getenv("AIGC_THRESHOLD", DEFAULT_THRESHOLD))
        self.daily_count = 0

    def check_articles(self, articles: list) -> dict:
        """检测多篇文章

        Args:
            articles: 文章列表

        Returns:
            检测报告: {total, passed, failed, results, daily_remaining}
        """
        results = []
        passed = 0
        failed = 0

        for article in articles:
            if self.daily_count >= DAILY_LIMIT:
                logger.warning(f"朱雀检测每日额度用尽 ({DAILY_LIMIT}次)，跳过剩余文章")
                break

            content = article.get("content", "")
            title = article.get("main_title", "")

            result = self._check_one(content, title)
            results.append({
                "title": title,
                "ai_probability": result.get("ai_probability", 1.0),
                "passed": result.get("passed", False),
                "retry_count": result.get("retry_count", 0),
            })

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
            "daily_used": self.daily_count,
            "daily_remaining": DAILY_LIMIT - self.daily_count,
            "threshold": self.threshold,
            "checked_at": datetime.now(self.tz).isoformat(),
        }

        logger.info(f"检测完成: {passed}/{len(results)} 通过 (阈值 {self.threshold})")
        return report

    def _check_one(self, content: str, title: str) -> dict:
        """检测单篇文章

        包含检测-重写循环：未通过→重写→再检测，最多 MAX_RETRIES 次
        """
        from humanizer.rewrite import Humanizer

        humanizer = Humanizer()
        current_content = content
        retry_count = 0

        while retry_count < MAX_RETRIES:
            if self.daily_count >= DAILY_LIMIT:
                logger.warning("每日额度用尽")
                return {"ai_probability": 1.0, "passed": False, "retry_count": retry_count}

            # 调用检测 API
            ai_prob = self._call_api(current_content)
            self.daily_count += 1

            if ai_prob is None:
                logger.error(f"检测 API 调用失败 [{title}]")
                return {"ai_probability": 1.0, "passed": False, "retry_count": retry_count}

            logger.info(f"检测 [{title[:20]}]: AI概率 {ai_prob:.1%} (第{retry_count+1}次)")

            if ai_prob <= self.threshold:
                logger.info(f"通过检测 [{title[:20]}]")
                return {"ai_probability": ai_prob, "passed": True, "retry_count": retry_count}

            # 未通过，重写后再检测
            retry_count += 1
            if retry_count < MAX_RETRIES:
                logger.info(f"未通过，重写第 {retry_count} 次...")
                current_content = humanizer._tier2_rewrite(current_content, title)
                time.sleep(1)  # 礼貌延迟

        return {"ai_probability": ai_prob, "passed": False, "retry_count": retry_count}

    def _call_api(self, content: str) -> float:
        """调用朱雀检测 API

        Returns:
            AI 生成概率 (0.0-1.0)，失败返回 None
        """
        if not self.api_key:
            logger.warning("未配置 ZHUQUE_API_KEY，跳过检测")
            # 降级: 用本地模式检测器估算
            from humanizer.patterns import PatternDetector
            detector = PatternDetector()
            report = detector.detect(content)
            return report["ai_score"] / 100.0

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = {"text": content[:5000]}  # 限制长度

            resp = requests.post(ZHUQUE_API, headers=headers, json=data, timeout=30)

            if resp.status_code == 429:
                logger.warning("朱雀 API 限流")
                return None

            resp.raise_for_status()
            result = resp.json()

            # 解析 AI 概率（根据实际 API 返回格式调整）
            ai_prob = result.get("data", {}).get("ai_probability", 0.5)
            return float(ai_prob)

        except Exception as e:
            logger.error(f"朱雀 API 调用失败: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    checker = ZhuqueChecker()
    test_articles = [{"main_title": "测试", "content": "这是一段测试文本。"}]
    report = checker.check_articles(test_articles)
    print(json.dumps(report, ensure_ascii=False, indent=2))
