"""AIGC 检测模块（v2）

说明：
- v2 增加 **Sapling AI Detector**（免费 API）作为首选真实检测来源。
- 检测优先级：Sapling API  >  朱雀 API（需 EdgeOne 网关）  >  本地模式（规则匹配）。
- 无论走哪种，只要配置了真实 API（Sapling 或 朱雀），就会启用
  "未通过 → 去 AI 味重写 → 再次检测" 的闭环（最多 MAX_RETRIES 次）。

环境变量：
- SAPLING_API_KEY      （选填）Sapling 免费 API key，启用 Sapling 检测
- ZHUQUE_API_KEY       （选填）朱雀 API key
- ZHUQUE_API_BASE_URL  （选填）朱雀 EdgeOne 网关地址，如 https://xxx.edgeone.app
- AIGC_THRESHOLD       （选填）通过阈值。本地/Sapling 用 0-100 分制，默认 25（越低越好）
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 25  # 本地/朱雀/Sapling 归一化到 0-100 分制；≤25 视为通过
MAX_RETRIES = 5  # 检测-重写循环最多 5 次

# Sapling 端点（免费，注册即得 key）
SAPLING_URL = "https://api.sapling.ai/api/v1/aidetect"


class AIGCChecker:
    """AIGC 检测器（Sapling/朱雀 API 优先，本地模式兜底）"""

    def __init__(self):
        self.sapling_key = os.getenv("SAPLING_API_KEY", "")
        self.api_key = os.getenv("ZHUQUE_API_KEY", "")
        self.api_base = os.getenv("ZHUQUE_API_BASE_URL", "")
        self.tz = timezone(timedelta(hours=8))
        self.threshold = float(os.getenv("AIGC_THRESHOLD", DEFAULT_THRESHOLD))

        # 决定模式
        if self.sapling_key:
            self.use_remote = True
            self.mode = "Sapling_API"
        elif self.api_key and self.api_base:
            self.use_remote = True
            self.mode = "朱雀API"
        else:
            self.use_remote = False
            self.mode = "本地模式检测"

        logger.info(f"AIGC检测模式: {self.mode}")
        logger.info(f"通过阈值: ≤ {self.threshold}")

    def check_articles(self, articles: list) -> dict:
        """检测多篇文章（含检测-重写循环）"""
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
            "provider": self.mode,
            "threshold": self.threshold,
            "checked_at": datetime.now(self.tz).isoformat(),
        }

        logger.info(f"检测完成: {passed}/{len(results)} 通过 (模式: {self.mode}, 阈值: {self.threshold})")
        return report

    def _check_one(self, article: dict, detector) -> dict:
        """检测单篇文章（含检测-重写循环）"""
        from humanizer.rewrite import Humanizer

        humanizer = Humanizer()
        title = article.get("main_title", "")
        retry_count = 0
        ai_score = 100.0
        last_mode = self.mode

        while retry_count < MAX_RETRIES:
            current_content = article.get("content", "")

            if self.use_remote:
                ai_score = self._call_remote_api(current_content)
                if ai_score is None:
                    logger.warning(f"{self.mode}调用失败，降级到本地模式")
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
                    "mode": last_mode,
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
            "mode": last_mode,
        }

    def _call_remote_api(self, content: str) -> float:
        """优先 Sapling，其次朱雀。失败返回 None（触发降级）。"""
        if self.sapling_key:
            try:
                return self._call_sapling(content)
            except Exception as e:
                logger.error(f"Sapling 调用失败: {e}")
                return None

        if self.api_key and self.api_base:
            try:
                return self._call_zhuque_api(content)
            except Exception as e:
                logger.error(f"朱雀 调用失败: {e}")
                return None

        return None

    def _call_sapling(self, content: str) -> float:
        """调用 Sapling AI Detector（免费 API）

        POST https://api.sapling.ai/api/v1/aidetect
        body: {"key": "<key>", "text": "...", "sent_scores": false}
        返回: score ∈ [0,1]，1=AI 生成，0=人工。这里转成 0-100 分制。
        """
        resp = requests.post(
            SAPLING_URL,
            json={"key": self.sapling_key, "text": content[:200000], "sent_scores": False},
            headers={"Content-Type": "application/json"},
            timeout=40,
        )
        resp.raise_for_status()
        result = resp.json()
        score = result.get("score", None)
        if score is None:
            return None
        # 0-1 → 0-100
        return float(score) * 100

    def _call_zhuque_api(self, content: str) -> float:
        """调用朱雀检测 API（需 EdgeOne 网关）"""
        if not self.api_key or not self.api_base:
            return None

        try:
            url = f"{self.api_base.rstrip('/')}/v1/providers/zhuque-text/classify"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = {"text": content[:5000], "is_merge": True}

            resp = requests.post(url, headers=headers, json=data, timeout=30)

            if resp.status_code == 429:
                logger.warning("朱雀 API 限流")
                return None

            resp.raise_for_status()
            result = resp.json()

            # 官方返回 labels_ratio：{"0":人工占比,"1":AI占比,"2":疑似AI占比}
            labels = result.get("labels_ratio", {})
            ai_prob = labels.get("1")
            if ai_prob is not None:
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
