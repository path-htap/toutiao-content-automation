"""飞书消息通知模块

通过飞书 Webhook 发送消息卡片，推送运行状态和成品。
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

# 飞书 Webhook API
FEISHU_WEBHOOK_API = "https://open.feishu.cn/open-apis/bot/v2/hook/"


class FeishuNotifier:
    """飞书消息通知器"""

    def __init__(self):
        self.webhook = os.getenv("FEISHU_WEBHOOK", "")
        self.webhook_secret = os.getenv("FEISHU_WEBHOOK_SECRET", "")
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.tz = timezone(timedelta(hours=8))

    def _gen_sign(self, timestamp: int) -> str:
        """生成飞书 Webhook 签名（HMAC-SHA256 + Base64）"""
        string_to_sign = f"{timestamp}\n{self.webhook_secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def send_text(self, text: str) -> bool:
        """发送纯文本消息"""
        return self._send({
            "msg_type": "text",
            "content": {"text": text}
        })

    def send_summary(self, articles: list, report: dict = None) -> bool:
        """发送运行摘要消息卡片

        Args:
            articles: 文章列表
            report: AIGC 检测报告
        """
        now = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M")

        # 构建文章列表
        article_items = []
        for i, article in enumerate(articles[:10]):  # 最多展示 10 篇
            title = article.get("main_title", f"文章{i+1}")
            style = article.get("style_name", "")
            ai_score = ""
            if report:
                for r in report.get("results", []):
                    if r.get("title", "") == title:
                        prob = r.get("ai_probability", 0)
                        passed = "✅" if r.get("passed") else "❌"
                        ai_score = f" | AI概率 {prob:.0%} {passed}"
                        break

            article_items.append({
                "title": f"{i+1}. {title}",
                "content": f"风格: {style}{ai_score}",
            })

        # 检测摘要
        detection_summary = ""
        if report:
            detection_summary = (
                f"\n\n📊 AIGC检测: {report.get('passed', 0)}/{report.get('total', 0)} 通过 "
                f"(剩余额度: {report.get('daily_remaining', 0)}次)"
            )

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"📰 今日头条文案自动化 - {now}"},
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"本次共生成 **{len(articles)}** 篇文案{detection_summary}"}
                    },
                    {"tag": "hr"},
                    *[
                        {
                            "tag": "div",
                            "fields": [
                                {"is_short": True, "text": {"tag": "lark_md", "content": f"**{item['title']}**"}},
                                {"is_short": True, "text": {"tag": "lark_md", "content": item["content"]}},
                            ]
                        }
                        for item in article_items
                    ],
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "请在飞书文档中审阅完整内容，回复 **发布** 即可发布，回复修改意见则重新生成。"}
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "✅ 全部发布"},
                                "type": "primary",
                                "value": {"action": "publish_all"}
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "📝 需要修改"},
                                "type": "default",
                                "value": {"action": "request_changes"}
                            },
                        ]
                    }
                ]
            }
        }

        return self._send(card)

    def send_error(self, phase: str, error: str) -> bool:
        """发送错误通知"""
        now = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M")
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"❌ 运行异常 - {now}"},
                    "template": "red"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"**阶段:** {phase}\n**错误:** {error[:500]}"}
                    },
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "请检查 GitHub Actions 日志，修复后重新触发。"}
                    }
                ]
            }
        }
        return self._send(card)

    def _send(self, payload: dict) -> bool:
        """发送消息到飞书 Webhook"""
        if not self.webhook:
            logger.warning("未配置 FEISHU_WEBHOOK，消息未发送")
            logger.info(f"消息内容: {json.dumps(payload, ensure_ascii=False)[:200]}")
            return False

        # 如果配置了签名密钥，则加上签名（飞书机器人开启了安全设置时需要）
        if self.webhook_secret:
            timestamp = int(time.time())
            sign = self._gen_sign(timestamp)
            payload["timestamp"] = str(timestamp)
            payload["sign"] = sign

        try:
            resp = requests.post(self.webhook, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") == 0:
                logger.info("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书发送失败: {result}")
                return False

        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notifier = FeishuNotifier()
    notifier.send_text("测试消息 - 今日头条文案自动化系统")
