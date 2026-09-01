"""飞书文档创建模块

通过飞书 OpenAPI 创建飞书文档，内嵌排版内容。
需配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET。
"""

import json
import logging
import os
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 飞书 OpenAPI
FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuDocCreator:
    """飞书文档创建器"""

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.tz = timezone(timedelta(hours=8))
        self._token = None
        self._token_expires = 0

    def _get_token(self) -> str:
        """获取飞书应用 access_token"""
        if self._token and time.time() < self._token_expires:
            return self._token

        if not self.app_id or not self.app_secret:
            logger.warning("未配置飞书应用凭证")
            return ""

        try:
            resp = requests.post(
                f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
            self._token_expires = time.time() + data.get("expire", 7200) - 60
            logger.info("飞书 token 获取成功")
            return self._token

        except Exception as e:
            logger.error(f"飞书 token 获取失败: {e}")
            return ""

    def create_doc(self, title: str, content: str) -> str:
        """创建飞书文档

        Args:
            title: 文档标题
            content: 文档内容

        Returns:
            文档 URL，失败返回空字符串
        """
        import time
        token = self._get_token()
        if not token:
            return ""

        try:
            # 1. 创建文档
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp = requests.post(
                f"{FEISHU_BASE}/docx/v1/documents",
                headers=headers,
                json={"title": title},
                timeout=10
            )
            resp.raise_for_status()
            doc_id = resp.json().get("document", {}).get("document_id", "")

            if not doc_id:
                logger.error("创建文档失败: 未获取 document_id")
                return ""

            # 2. 写入内容
            blocks = self._content_to_blocks(content)
            requests.post(
                f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
                headers=headers,
                json={"children": blocks},
                timeout=10
            )

            url = f"https://bytedance.feishu.cn/docx/{doc_id}"
            logger.info(f"飞书文档创建成功: {url}")
            return url

        except Exception as e:
            logger.error(f"飞书文档创建失败: {e}")
            return ""

    def _content_to_blocks(self, content: str) -> list:
        """将文本内容转换为飞书文档 Block 格式"""
        blocks = []
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            blocks.append({
                "block_type": 2,  # Text block
                "text": {
                    "elements": [{"text_run": {"content": line}}],
                    "style": {}
                }
            })
        return blocks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    creator = FeishuDocCreator()
    # creator.create_doc("测试文档", "这是测试内容\n第二段")
    print("运行需配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
