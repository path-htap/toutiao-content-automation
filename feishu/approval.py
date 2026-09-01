"""飞书审批门模块

实现"飞书审批门"流程：生成成品先发飞书审阅，
用户回复"发布"才正式发布，超时 24 小时自动归档。
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class ApprovalGate:
    """飞书审批门"""

    def __init__(self):
        self.tz = timezone(timedelta(hours=8))
        self.output_dir = Path(__file__).parent.parent / "output"

    def submit_for_review(self, articles: list, report: dict = None) -> bool:
        """提交成品等待审阅

        Args:
            articles: 文章列表
            report: 检测报告

        Returns:
            是否提交成功
        """
        # 保存审批状态文件
        state = {
            "status": "pending_review",
            "submitted_at": datetime.now(self.tz).isoformat(),
            "expires_at": (datetime.now(self.tz) + timedelta(hours=24)).isoformat(),
            "article_count": len(articles),
            "articles": [
                {
                    "title": a.get("main_title", ""),
                    "style": a.get("style_name", ""),
                    "ai_probability": self._get_ai_prob(a.get("main_title", ""), report),
                }
                for a in articles
            ],
        }

        state_file = self.output_dir / "approval_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        logger.info(f"已提交 {len(articles)} 篇文章待审阅，24小时内有效")
        return True

    def check_approval_status(self) -> dict:
        """检查审批状态

        Returns:
            {status, articles, submitted_at, expires_at}
        """
        state_file = self.output_dir / "approval_state.json"
        if not state_file.exists():
            return {"status": "no_pending"}

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        # 检查是否过期
        expires_at = datetime.fromisoformat(state.get("expires_at", ""))
        if datetime.now(self.tz) > expires_at:
            state["status"] = "expired"
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info("审批已过期（24小时未回复），自动归档")

        return state

    def _get_ai_prob(self, title: str, report: dict) -> float:
        """从报告中获取文章的 AI 概率"""
        if not report:
            return 0.0
        for r in report.get("results", []):
            if r.get("title", "") == title:
                return r.get("ai_probability", 0.0)
        return 0.0

    def mark_published(self) -> bool:
        """标记为已发布"""
        state_file = self.output_dir / "approval_state.json"
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["status"] = "published"
            state["published_at"] = datetime.now(self.tz).isoformat()
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info("文章已标记为发布")
        return True

    def mark_archived(self) -> bool:
        """标记为已归档（未发布）"""
        state_file = self.output_dir / "approval_state.json"
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["status"] = "archived"
            state["archived_at"] = datetime.now(self.tz).isoformat()
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info("文章已归档（未发布）")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gate = ApprovalGate()
    status = gate.check_approval_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
