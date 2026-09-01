"""飞书文档创建模块

通过飞书 OpenAPI 创建文档，将文章内容排版后写入飞书文档，
方便用户在手机上审阅和发布。
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

# 飞书 OpenAPI 基础地址
FEISHU_OPEN_API = "https://open.feishu.cn/open-apis"


class FeishuDocCreator:
    """飞书文档创建器"""

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.tz = timezone(timedelta(hours=8))
        self._tenant_token = None
        self._token_expire_time = 0

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（自动缓存和刷新）"""
        if not self.app_id or not self.app_secret:
            return ""

        # 检查缓存是否还有效（提前5分钟过期）
        if self._tenant_token and time.time() < self._token_expire_time - 300:
            return self._tenant_token

        try:
            resp = requests.post(
                f"{FEISHU_OPEN_API}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                self._tenant_token = data.get("tenant_access_token", "")
                self._token_expire_time = time.time() + data.get("expire", 7200)
                logger.info("获取飞书 tenant_access_token 成功")
                return self._tenant_token
            else:
                logger.error(f"获取 token 失败: {data}")
                return ""
        except Exception as e:
            logger.error(f"获取 token 异常: {e}")
            return ""

    def _headers(self) -> dict:
        """构造请求头"""
        token = self._get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def create_article_doc(self, article: dict) -> str:
        """创建单篇文章的飞书文档

        Args:
            article: 文章字典

        Returns:
            文档链接 URL
        """
        if not self.app_id or not self.app_secret:
            logger.warning("未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，跳过文档创建")
            return ""

        title = article.get("main_title", "未命名文章")
        content = article.get("content", "")
        summary = article.get("summary", "")
        conclusion = article.get("conclusion", "")
        images = article.get("images", [])

        # 构造文档内容（飞书 Docx 使用 Block 格式，这里先用纯文本+换行的简化方式）
        # 由于飞书新版文档 API 比较复杂，我们先创建文档，然后用富文本方式写入
        # 简化版：直接创建一个空白文档，标题为文章标题

        try:
            # 第一步：创建文档
            resp = requests.post(
                f"{FEISHU_OPEN_API}/docx/v1/documents",
                headers=self._headers(),
                json={
                    "title": title,
                    "folder_token": "",  # 放到我的空间根目录
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.error(f"创建文档失败: {data}")
                return ""

            doc_info = data.get("data", {}).get("document", {})
            document_id = doc_info.get("document_id", "")
            doc_url = f"https://feishu.cn/docx/{document_id}"

            logger.info(f"飞书文档创建成功: {title}")
            logger.info(f"文档链接: {doc_url}")

            # 第二步：设置权限（企业内可阅读，否则用户打不开）
            self._set_doc_permission(document_id)

            # 第三步：写入内容
            blocks = self._build_blocks(article)
            self._write_blocks(document_id, blocks)

            return doc_url

        except Exception as e:
            logger.error(f"创建文档异常: {e}")
            return ""

    def _build_blocks(self, article: dict) -> list:
        """构造飞书文档 Block 列表"""
        blocks = []
        block_id = 0

        def next_id():
            nonlocal block_id
            bid = f"blk_{block_id}"
            block_id += 1
            return bid

        # 副标题
        sub_title = article.get("sub_title", "")
        if sub_title:
            blocks.append({
                "block_id": next_id(),
                "block_type": 3,  # heading2
                "heading2": {
                    "elements": [
                        {
                            "text_run": {
                                "content": sub_title,
                                "text_element_style": {},
                            }
                        }
                    ],
                    "style": {},
                },
            })

        # 摘要
        summary = article.get("summary", "")
        if summary:
            blocks.append({
                "block_id": next_id(),
                "block_type": 20,  # callout（引用/提示框）
                "callout": {
                    "elements": [
                        {
                            "text_run": {
                                "content": f"📝 {summary}",
                                "text_element_style": {},
                            }
                        }
                    ],
                    "background_color": 2,  # 灰色背景
                    "border_color": 2,
                },
            })

        # 正文段落
        content = article.get("content", "")
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        for para in paragraphs:
            blocks.append({
                "block_id": next_id(),
                "block_type": 2,  # text
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": para,
                                "text_element_style": {},
                            }
                        }
                    ],
                    "style": {},
                },
            })

        # 结语
        conclusion = article.get("conclusion", "")
        if conclusion:
            blocks.append({
                "block_id": next_id(),
                "block_type": 20,  # callout
                "callout": {
                    "elements": [
                        {
                            "text_run": {
                                "content": f"💡 {conclusion}",
                                "text_element_style": {},
                            }
                        }
                    ],
                    "background_color": 1,  # 蓝色背景
                    "border_color": 1,
                },
            })

        # 配图信息（如果有）
        images = article.get("images", [])
        if images:
            blocks.append({
                "block_id": next_id(),
                "block_type": 3,  # heading2
                "heading2": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "📷 配图预览",
                                "text_element_style": {},
                            }
                        }
                    ],
                    "style": {},
                },
            })
            for img in images:
                img_url = img.get("url", "")
                img_alt = img.get("alt", "图片")
                blocks.append({
                    "block_id": next_id(),
                    "block_type": 2,  # text
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": f"[{img_alt}]({img_url})",
                                    "text_element_style": {"link": {"url": img_url}},
                                }
                            }
                        ],
                        "style": {},
                    },
                })

        return blocks

    def _write_blocks(self, document_id: str, blocks: list) -> bool:
        """将 Block 写入文档（追加到文档末尾）"""
        try:
            resp = requests.post(
                f"{FEISHU_OPEN_API}/docx/v1/documents/{document_id}/blocks/batch_create",
                headers=self._headers(),
                json={
                    "index": -1,  # 追加到末尾
                    "children": blocks,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                logger.info(f"文档内容写入成功: {len(blocks)} 个块")
                return True
            else:
                logger.error(f"文档内容写入失败: {data}")
                return False
        except Exception as e:
            logger.error(f"文档内容写入异常: {e}")
            return False

    def _set_doc_permission(self, document_id: str) -> bool:
        """设置文档权限为企业内可阅读

        否则创建的文档只有机器人自己能访问，用户打不开。
        """
        try:
            resp = requests.patch(
                f"{FEISHU_OPEN_API}/drive/v1/permissions/{document_id}/public",
                headers=self._headers(),
                params={"type": "docx"},
                json={
                    "link_share_entity": "tenant_viewable",  # 企业内可阅读
                    "permission_entity": "view",
                    "comment_entity": "open",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                logger.info(f"文档权限设置成功: 企业内可阅读")
                return True
            else:
                logger.warning(f"文档权限设置失败: {data}")
                # 权限设置失败不影响主流程，至少文档创建成功了
                return False
        except Exception as e:
            logger.warning(f"文档权限设置异常: {e}")
            return False

    def create_summary_doc(self, articles: list, report: dict = None) -> str:
        """创建汇总文档（包含所有文章的索引页）

        Args:
            articles: 文章列表
            report: AIGC 检测报告

        Returns:
            文档链接 URL
        """
        if not self.app_id or not self.app_secret:
            logger.warning("未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，跳过汇总文档创建")
            return ""

        today = datetime.now(self.tz).strftime("%Y年%m月%d日")
        title = f"📰 今日头条文案自动化 - {today} 汇总"

        try:
            # 创建汇总文档
            resp = requests.post(
                f"{FEISHU_OPEN_API}/docx/v1/documents",
                headers=self._headers(),
                json={"title": title},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.error(f"创建汇总文档失败: {data}")
                return ""

            doc_info = data.get("data", {}).get("document", {})
            document_id = doc_info.get("document_id", "")
            doc_url = f"https://feishu.cn/docx/{document_id}"

            # 先为每篇文章创建单独的文档
            article_docs = []
            for article in articles:
                url = self.create_article_doc(article)
                if url:
                    article_docs.append({
                        "title": article.get("main_title", ""),
                        "url": url,
                        "style": article.get("style_name", ""),
                    })

            # 写入汇总内容
            blocks = self._build_summary_blocks(articles, article_docs, report)
            self._write_blocks(document_id, blocks)

            logger.info(f"汇总文档创建成功: {doc_url}")
            return doc_url

        except Exception as e:
            logger.error(f"创建汇总文档异常: {e}")
            return ""

    def _build_summary_blocks(self, articles: list, article_docs: list, report: dict = None) -> list:
        """构造汇总文档的 Block 列表"""
        blocks = []
        block_id = 0

        def next_id():
            nonlocal block_id
            bid = f"blk_{block_id}"
            block_id += 1
            return bid

        # 概览
        blocks.append({
            "block_id": next_id(),
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": f"本期共生成 **{len(articles)}** 篇文案",
                            "text_element_style": {},
                        }
                    }
                ],
                "style": {},
            },
        })

        # AIGC 检测摘要
        if report:
            passed = report.get("passed", 0)
            total = report.get("total", 0)
            remaining = report.get("daily_remaining", "未知")
            blocks.append({
                "block_id": next_id(),
                "block_type": 20,
                "callout": {
                    "elements": [
                        {
                            "text_run": {
                                "content": f"📊 AIGC 检测: {passed}/{total} 篇通过 | 今日剩余额度: {remaining} 次",
                                "text_element_style": {},
                            }
                        }
                    ],
                    "background_color": 1 if passed == total else 3,
                    "border_color": 1 if passed == total else 3,
                },
            })

        # 分隔线
        blocks.append({
            "block_id": next_id(),
            "block_type": 22,  # divider
            "divider": {},
        })

        # 文章列表
        blocks.append({
            "block_id": next_id(),
            "block_type": 3,
            "heading2": {
                "elements": [
                    {"text_run": {"content": "📋 文章列表", "text_element_style": {}}}
                ],
                "style": {},
            },
        })

        for i, (article, doc) in enumerate(zip(articles, article_docs), 1):
            title = article.get("main_title", "")
            style = article.get("style_name", "")
            summary = article.get("summary", "")
            doc_url = doc.get("url", "")

            # 标题（带链接）
            blocks.append({
                "block_id": next_id(),
                "block_type": 4,  # heading3
                "heading3": {
                    "elements": [
                        {
                            "text_run": {
                                "content": f"{i}. {title}",
                                "text_element_style": {"link": {"url": doc_url}},
                            }
                        }
                    ],
                    "style": {},
                },
            })

            # 风格 + 摘要
            blocks.append({
                "block_id": next_id(),
                "block_type": 2,
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": f"风格: {style}\n{summary}",
                                "text_element_style": {},
                            }
                        }
                    ],
                    "style": {},
                },
            })

            # 空行
            blocks.append({
                "block_id": next_id(),
                "block_type": 2,
                "text": {"elements": [], "style": {}},
            })

        return blocks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    creator = FeishuDocCreator()
    # 测试创建（需要配置 App ID/Secret）
    if creator.app_id and creator.app_secret:
        test_article = {
            "main_title": "测试文章",
            "sub_title": "测试副标题",
            "summary": "这是一篇测试文章的摘要",
            "content": "第一段内容。\n\n第二段内容。\n\n第三段内容。",
            "conclusion": "结语：测试完成。",
            "images": [],
        }
        url = creator.create_article_doc(test_article)
        print(f"测试文档链接: {url}")
    else:
        print("请先配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
