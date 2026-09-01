"""语义配图匹配

LLM 分析段落语义，插入配图标记，匹配图片。
参考: image-match-skills 项目逻辑
"""

import json
import logging

logger = logging.getLogger(__name__)

MATCH_PROMPT = """请分析以下文章内容，为每个段落推荐一个配图搜索关键词。

要求:
1. 分析每个段落的主题和语义
2. 为需要配图的段落推荐 2-3 个英文搜索关键词
3. 不是每个段落都需要配图（通常 3-5 张即可）
4. 返回 JSON 格式:

```json
[
  {
    "paragraph_index": 0,
    "needs_image": true,
    "keywords": "technology AI",
    "reason": "段落讨论AI技术，配科技感图片"
  }
]
```"""


class ImageMatcher:
    """图片匹配器"""

    def __init__(self, searcher):
        self.searcher = searcher

    def match_images(self, articles: list) -> list:
        """为文章列表匹配图片

        Args:
            articles: 文章列表

        Returns:
            添加了 images 字段的文章列表
        """
        results = []
        for article in articles:
            article_with_images = self._match_one(article)
            results.append(article_with_images)

        logger.info(f"配图匹配完成: {len(results)} 篇")
        return results

    def _match_one(self, article: dict) -> dict:
        """为单篇文章匹配图片"""
        content = article.get("content", "")
        paragraphs = content.split("\n")

        # 用 LLM 分析段落
        match_plan = self._analyze_paragraphs(paragraphs, article)

        # 搜索图片
        images = []
        for plan in match_plan:
            if plan.get("needs_image"):
                keywords = plan.get("keywords", "")
                if keywords:
                    photos = self.searcher.search(keywords, per_page=2)
                    if photos:
                        images.append({
                            "paragraph_index": plan.get("paragraph_index", 0),
                            "keywords": keywords,
                            "url": photos[0]["url"],
                            "thumb_url": photos[0]["thumb_url"],
                            "alt": photos[0]["alt"],
                            "source": photos[0]["source"],
                        })

        article["images"] = images
        logger.info(f"配图: {article.get('main_title', '')} → {len(images)} 张")
        return article

    def _analyze_paragraphs(self, paragraphs: list, article: dict) -> list:
        """用 LLM 分析段落，决定配图位置"""
        from writers.article_agent import LLMClient

        title = article.get("main_title", "")
        summary = article.get("summary", "")

        content_text = "\n".join(
            f"[{i}] {p[:100]}" for i, p in enumerate(paragraphs) if p.strip()
        )

        user_prompt = f"文章标题: {title}\n摘要: {summary}\n段落:\n{content_text}"

        try:
            client = LLMClient()
            response = client.chat([
                {"role": "system", "content": MATCH_PROMPT},
                {"role": "user", "content": user_prompt}
            ])
            content = response.choices[0].message.content

            # 解析 JSON
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end]

            return json.loads(content)

        except Exception as e:
            logger.error(f"段落分析失败: {e}")
            # 降级: 为前 3 个段落配图
            return [
                {"paragraph_index": 0, "needs_image": True, "keywords": title, "reason": "封面"}
            ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from images.search_api import ImageSearcher
    searcher = ImageSearcher()
    matcher = ImageMatcher(searcher)
    test_article = {"main_title": "AI技术", "summary": "AI", "content": "段落1\n段落2"}
    result = matcher._match_one(test_article)
    print(json.dumps(result, ensure_ascii=False, indent=2))
