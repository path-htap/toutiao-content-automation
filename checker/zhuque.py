"""AIGC 检测模块（v3）

说明：
- v3 增加 **LLM 判定器**作为首选免费真实检测来源（用已有的 ZHIPU_API_KEY / SILICONFLOW_API_KEY）。
- 检测优先级：LLM 判定器  >  朱雀 API（需 EdgeOne 网关）  >  Sapling API  >  本地模式。
- 无论走哪种，只要配置了真实检测源（LLM/朱雀/Sapling），就会启用
  "未通过 → 去 AI 味重写 → 再次检测" 的闭环（最多 MAX_RETRIES 次）。

环境变量：
- ZHIPU_API_KEY        （推荐）智谱 AI 免费 key，走 LLM 判定器
- SILICONFLOW_API_KEY  （备选）硅基流动免费 key，走 LLM 判定器
- ZHUQUE_API_KEY       （选填）朱雀 API key
- ZHUQUE_API_BASE_URL  （选填）朱雀 EdgeOne 网关地址
- SAPLING_API_KEY      （选填）Sapling 免费 API key
- AIGC_THRESHOLD       （选填）通过阈值，0-100 分制，默认 25（越低越好）
- AIGC_USE_LLM         （选填）"0" 禁用 LLM 判定器
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 25  # 归一化到 0-100 分制；≤25 视为通过
MAX_RETRIES = 5  # 检测-重写循环最多 5 次

# 各检测源端点
SAPLING_URL = "https://api.sapling.ai/api/v1/aidetect"

# LLM 判定器 prompt（让它输出 0-100 的 AI 概率分，越低越像人写）
LLM_JUDGE_PROMPT = """你是一个专业的 AI 生成内容（AIGC）检测器。请判断下面这段文本是由 AI 生成的还是人工写的。

判断依据：
- 是否存在 AI 常用套路语（"值得注意的是""综上所述""首先...其次...最后"、排比并列、过度工整）
- 是否缺乏具体细节、个人观点、口语化、情感起伏
- 是否句式过于均匀、用词过于规范
- 是否像真人博主那样有语气词、反问、个人吐槽、数字细节

请只输出一个 0 到 100 的整数（0=100%人工、100=100%AI），不要输出任何其他文字。

文本内容：
{content}
"""


class AIGCChecker:
    """AIGC 检测器（LLM 判定器 API 优先，本地模式兜底）"""

    def __init__(self):
        self.sapling_key = os.getenv("SAPLING_API_KEY", "")
        self.api_key = os.getenv("ZHUQUE_API_KEY", "")
        self.api_base = os.getenv("ZHUQUE_API_BASE_URL", "")
        self.zhipu_key = os.getenv("ZHIPU_API_KEY", "")
        self.siliconflow_key = os.getenv("SILICONFLOW_API_KEY", "")
        self.tz = timezone(timedelta(hours=8))
        self.threshold = float(os.getenv("AIGC_THRESHOLD", DEFAULT_THRESHOLD))
        self.use_llm = os.getenv("AIGC_USE_LLM", "1") != "0"

        # 决定模式
        self.use_remote = False
        if self.use_llm and (self.zhipu_key or self.siliconflow_key):
            self.use_remote = True
            self.mode = "LLM判定器"
        elif self.api_key and self.api_base:
            self.use_remote = True
            self.mode = "朱雀API"
        elif self.sapling_key:
            self.use_remote = True
            self.mode = "Sapling_API"
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
        """优先 LLM 判定器，其次朱雀，再 Sapling。失败返回 None（触发降级）。"""
        if self.use_llm and (self.zhipu_key or self.siliconflow_key):
            try:
                return self._call_llm_judge(content)
            except Exception as e:
                logger.error(f"LLM 判定器调用失败: {e}")
                return None

        if self.api_key and self.api_base:
            try:
                return self._call_zhuque_api(content)
            except Exception as e:
                logger.error(f"朱雀 调用失败: {e}")
                return None

        if self.sapling_key:
            try:
                return self._call_sapling(content)
            except Exception as e:
                logger.error(f"Sapling 调用失败: {e}")
                return None

        return None

    def _call_llm_judge(self, content: str) -> float:
        """调用 LLM（智谱/硅基 免费模型）做 AI 判定，返回 0-100 分。
        使用与文章生成相同的 LLMClient，保证 key/模型已配置可用。
        """
        from writers.article_agent import LLMClient

        client = LLMClient()  # 自动选有 key 的 provider（zhipu 优先）
        prompt = LLM_JUDGE_PROMPT.format(content=content[:3000])  # 判定用文本上限，控制成本
        resp = client.chat(
            [{"role": "system", "content": prompt}],
            max_tokens=16,
            temperature=0.0,
        )
        text = resp.choices[0].message.content.strip()
        # 只取数字
        import re
        m = re.search(r"\d+(\.\d+)?", text)
        if not m:
            return None
        score = float(m.group(0))  # 用 group(0)，避免无小数时 group(1) 为 None
        if score > 100:
            score = 100.0
        if score < 0:
            score = 0.0
        return score

    def _call_sapling(self, content: str) -> float:
        """调用 Sapling AI Detector（免费 API）"""
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
