"""HTML 排版布局模块

使用 Jinja2 模板引擎，将文案+图片生成为自包含 HTML 成品。
支持多平台版式: 今日头条 / 公众号 / 小红书
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# 模板目录
TEMPLATE_DIR = Path(__file__).parent / "templates"

# 基础模板（内联，无需外部文件）
BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ main_title }}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "Noto Sans CJK SC", "Helvetica Neue", sans-serif;
       max-width: 680px; margin: 0 auto; padding: 20px; color: #333; line-height: 1.8; }
h1 { font-size: 24px; text-align: center; margin: 20px 0 10px; color: #1a1a1a; }
h2 { font-size: 18px; color: #666; text-align: center; font-weight: normal; margin-bottom: 20px; }
.summary { background: #f5f5f5; padding: 15px; border-radius: 8px; margin-bottom: 25px;
           color: #666; font-size: 14px; }
.content { font-size: 16px; }
.content p { margin-bottom: 20px; }
.content img { max-width: 100%; border-radius: 8px; margin: 15px 0; display: block; }
.img-caption { text-align: center; font-size: 12px; color: #999; margin-top: -10px; margin-bottom: 20px; }
.conclusion { border-top: 2px solid #eee; padding-top: 20px; margin-top: 30px;
              font-weight: bold; color: #1a1a1a; }
.footer { text-align: center; margin-top: 40px; font-size: 12px; color: #ccc;
          border-top: 1px solid #eee; padding-top: 15px; }
@media (max-width: 375px) { body { padding: 12px; } h1 { font-size: 20px; } }
</style>
</head>
<body>
<h1>{{ main_title }}</h1>
<h2>{{ sub_title }}</h2>
<div class="summary">{{ summary }}</div>
<div class="content">
{{ content_html | safe }}
</div>
<div class="conclusion">{{ conclusion }}</div>
<div class="footer">由今日头条文案自动化系统生成 · {{ date }}</div>
</body>
</html>"""


class HTMLBuilder:
    """HTML 排版生成器"""

    def __init__(self):
        self.tz = timezone(timedelta(hours=8))

    def build_all(self, articles: list, template_name: str = "toutiao") -> list:
        """为所有文章生成 HTML

        Args:
            articles: 文章列表
            template_name: 模板名称 (toutiao/wechat/xiaohongshu)

        Returns:
            HTML 文件路径列表
        """
        results = []
        output_dir = Path(__file__).parent.parent / "output" / "html"
        output_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(self.tz).strftime("%Y%m%d")

        for i, article in enumerate(articles):
            html = self._build_one(article, template_name)

            title = article.get("main_title", f"article_{i}")
            # 文件名安全处理
            safe_title = "".join(c for c in title if c.isalnum() or c in "_-")[:30]
            filename = f"{today}_{i+1}_{safe_title}.html"
            filepath = output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            results.append({
                "file": str(filepath),
                "title": title,
                "style": article.get("style_name", ""),
            })
            logger.info(f"生成 HTML: {filename}")

        return results

    def _build_one(self, article: dict, template_name: str) -> str:
        """生成单篇 HTML"""
        # 构建 content HTML（插入图片）
        content = article.get("content", "")
        paragraphs = content.split("\n")
        images = article.get("images", [])

        # 图片按段落索引分组
        image_map = {}
        for img in images:
            idx = img.get("paragraph_index", 0)
            if idx not in image_map:
                image_map[idx] = []
            image_map[idx].append(img)

        # 构建 HTML 段落
        html_parts = []
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            html_parts.append(f"<p>{para}</p>")

            # 插入图片
            if i in image_map:
                for img in image_map[i]:
                    html_parts.append(
                        f'<img src="{img["url"]}" alt="{img.get("alt", "")}">'
                    )
                    html_parts.append(
                        f'<div class="img-caption">图源: {img.get("source", "")}</div>'
                    )

        content_html = "\n".join(html_parts)

        # 渲染模板
        from jinja2 import Template
        template = Template(BASE_TEMPLATE)
        html = template.render(
            main_title=article.get("main_title", ""),
            sub_title=article.get("sub_title", ""),
            summary=article.get("summary", ""),
            content_html=content_html,
            conclusion=article.get("conclusion", ""),
            date=datetime.now(self.tz).strftime("%Y-%m-%d"),
        )

        return html


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    builder = HTMLBuilder()
    test_article = {
        "main_title": "测试标题",
        "sub_title": "测试副标题",
        "summary": "测试摘要",
        "content": "第一段内容\n第二段内容\n第三段内容",
        "conclusion": "结语",
        "images": [],
    }
    results = builder.build_all([test_article])
    print(json.dumps(results, ensure_ascii=False, indent=2))
