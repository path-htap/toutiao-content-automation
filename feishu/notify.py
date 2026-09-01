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
FEISHU_OPEN_API = "https://open.feishu.cn/open-apis"


class FeishuNotifier:
    """飞书消息通知器"""

    def __init__(self):
        self.webhook = os.getenv("FEISHU_WEBHOOK", "")
        self.webhook_secret = os.getenv("FEISHU_WEBHOOK_SECRET", "")
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.tz = timezone(timedelta(hours=8))
        self._tenant_access_token = None
        self._token_expire_time = 0

    def _gen_sign(self, timestamp: int) -> str:
        """生成飞书 Webhook 签名（HMAC-SHA256 + Base64）"""
        string_to_sign = f"{timestamp}\n{self.webhook_secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def _get_tenant_token(self) -> str:
        """获取飞书 tenant_access_token（用于上传图片等应用级操作）"""
        if not self.app_id or not self.app_secret:
            return ""

        # 缓存未过期则直接返回
        if self._tenant_access_token and time.time() < self._token_expire_time - 60:
            return self._tenant_access_token

        try:
            resp = requests.post(
                f"{FEISHU_OPEN_API}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._tenant_access_token = data.get("tenant_access_token", "")
                self._token_expire_time = time.time() + data.get("expire", 7200)
                logger.info("飞书 tenant_access_token 获取成功")
                return self._tenant_access_token
            else:
                logger.error(f"获取 tenant_access_token 失败: {data}")
                return ""
        except Exception as e:
            logger.error(f"获取 tenant_access_token 异常: {e}")
            return ""

    def _upload_image(self, image_url: str) -> str:
        """上传图片到飞书，返回 image_key

        飞书消息中显示图片需要先上传获取 image_key。
        失败则返回空字符串。
        """
        token = self._get_tenant_token()
        if not token:
            return ""

        try:
            # 先下载图片
            img_resp = requests.get(image_url, timeout=15)
            img_resp.raise_for_status()
            img_data = img_resp.content

            # 上传到飞书
            resp = requests.post(
                f"{FEISHU_OPEN_API}/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                data={"image_type": "message"},
                files={"image": ("cover.jpg", img_data, "image/jpeg")},
                timeout=20,
            )
            data = resp.json()
            if data.get("code") == 0:
                image_key = data.get("data", {}).get("image_key", "")
                logger.info(f"图片上传成功: {image_key}")
                return image_key
            else:
                logger.warning(f"图片上传失败: {data}")
                return ""
        except Exception as e:
            logger.warning(f"图片上传异常: {e}")
            return ""

    def send_text(self, text: str) -> bool:
        """发送纯文本消息"""
        return self._send({
            "msg_type": "text",
            "content": {"text": text}
        })

    def send_summary(self, articles: list, report: dict = None, doc_url: str = "") -> bool:
        """发送运行摘要消息卡片

        Args:
            articles: 文章列表
            report: AIGC 检测报告
            doc_url: 飞书汇总文档链接
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
                        "text": {"tag": "lark_md", "content": (
                            f"📄 [点此查看完整文档]({doc_url})"
                            if doc_url else
                            "💡 配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 可自动创建飞书文档"
                        )}
                    },
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

    def send_articles(self, articles: list) -> bool:
        """发送完整文章内容（交互式卡片 + 图片直接显示）

        每篇文章一条交互卡片消息，包含：
        - 封面图（直接显示，不是链接）
        - 标题、副标题
        - 正文内容（节选 + 展开/收起）
        - 结语
        """
        if not articles:
            return False

        logger.info(f"发送文章到飞书: {len(articles)} 篇")
        all_ok = True

        for i, article in enumerate(articles, 1):
            title = article.get("main_title", f"文章{i}")
            sub_title = article.get("sub_title", "")
            content = article.get("content", "")
            conclusion = article.get("conclusion", "")
            style = article.get("style_name", "")
            images = article.get("images", [])

            # 上传封面图（如果有）
            cover_image_key = ""
            if images:
                cover_url = images[0].get("url", "")
                if cover_url:
                    cover_image_key = self._upload_image(cover_url)

            # 构造卡片元素
            elements = []

            # 封面图（有 image_key 就直接显示图）
            if cover_image_key:
                elements.append({
                    "tag": "img",
                    "img_key": cover_image_key,
                    "alt": {"tag": "plain_text", "content": "封面图"},
                    "mode": "fit_horizontal",
                })
                elements.append({"tag": "hr"})

            # 副标题
            if sub_title:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"💬 *{sub_title}*"
                    }
                })

            # 风格标签
            if style:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🏷 风格: {style} ｜ 第 {i}/{len(articles)} 篇"
                    }
                })

            elements.append({"tag": "hr"})

            # 正文（分成多段显示）
            paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
            for para in paragraphs[:8]:  # 最多显示 8 段，防止太长
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": para
                    }
                })

            if len(paragraphs) > 8:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"_...（还有 {len(paragraphs) - 8} 段）_"
                    }
                })

            elements.append({"tag": "hr"})

            # 结语
            if conclusion:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"💡 **结语**: {conclusion}"
                    }
                })

            # 如果没图片，加个提示
            if not images:
                elements.append({
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "⚠️ 未找到匹配的配图"}
                    ]
                })

            # 组装卡片
            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"[{i}/{len(articles)}] {title}"
                        },
                        "template": "blue"
                    },
                    "elements": elements
                }
            }

            ok = self._send(card)
            if not ok:
                all_ok = False

            # 稍微间隔一下，避免触发限流
            time.sleep(0.5)

        return all_ok

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
