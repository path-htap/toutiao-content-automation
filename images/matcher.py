"""语义配图匹配

策略：
1. 优先用 LLM 分析段落语义，推荐英文关键词
2. 如果 LLM 失败或搜索结果为 0，降级用标题/关键词搜
3. 多轮搜索：标题 → 核心词 → 通用话题词，确保一定有图
"""

import json
import logging

logger = logging.getLogger(__name__)

MATCH_PROMPT = """请分析以下文章内容，为每个段落推荐一个配图搜索关键词（英文）。

要求:
1. 分析每个段落的主题和语义
2. 为需要配图的段落推荐 1-2 个简单的英文搜索关键词（2-3个单词即可）
3. 不是每个段落都需要配图（通常 3-5 张即可）
4. 关键词要通用、常见，确保 Pexels 能搜到图，不要太具体
5. 返回 JSON 格式:

```json
[
  {
    "paragraph_index": 0,
    "needs_image": true,
    "keywords": "fishing lake",
    "reason": "钓鱼场景"
  }
]
```"""


# 话题分类 → 通用搜索关键词映射（保底用）
TOPIC_KEYWORDS_MAP = {
    "社会": ["people", "city street", "crowd"],
    "科技": ["technology", "digital", "computer"],
    "财经": ["business", "money", "stock market"],
    "娱乐": ["entertainment", "celebrity", "concert"],
    "体育": ["sports", "athlete", "stadium"],
    "健康": ["health", "doctor", "hospital"],
    "教育": ["education", "school", "student"],
    "旅游": ["travel", "airplane", "tourist"],
    "美食": ["food", "restaurant", "cooking"],
    "汽车": ["car", "traffic", "highway"],
    "房产": ["house", "building", "real estate"],
    "安全": ["safety", "police", "emergency"],
    "国际": ["world", "globe", "international"],
    "军事": ["soldier", "military", "army"],
    "自然": ["nature", "mountain", "forest"],
    "动物": ["animals", "wildlife", "pets"],
    "钓鱼": ["fishing", "lake", "fish"],
    "消费": ["shopping", "market", "money"],
    "天气": ["weather", "clouds", "sunset"],
    "事故": ["emergency", "firefighter", "police"],
    "默认": ["news", "city", "people"],
}


class ImageMatcher:
    """图片匹配器"""

    def __init__(self, searcher):
        self.searcher = searcher

    def match_images(self, articles: list) -> list:
        """为文章列表匹配图片"""
        results = []
        for article in articles:
            article_with_images = self._match_one(article)
            results.append(article_with_images)

        logger.info(f"配图匹配完成: {len(results)} 篇")
        return results

    def _match_one(self, article: dict) -> dict:
        """为单篇文章匹配图片（多轮搜索保底）"""
        title = article.get("main_title", "")
        content = article.get("content", "")
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

        images = []

        # 第一轮：用 LLM 分析段落，推荐关键词
        try:
            match_plan = self._analyze_paragraphs(paragraphs, article)
            for plan in match_plan[:5]:  # 最多 5 张
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
        except Exception as e:
            logger.warning(f"LLM 配图分析失败: {e}")

        # 第二轮：如果图片不足，用标题关键词搜
        if len(images) < 3:
            needed = 3 - len(images)
            title_keywords = self._extract_keywords(title)
            for kw in title_keywords[:needed]:
                photos = self.searcher.search(kw, per_page=2)
                if photos:
                    images.append({
                        "paragraph_index": len(images),
                        "keywords": kw,
                        "url": photos[0]["url"],
                        "thumb_url": photos[0]["thumb_url"],
                        "alt": photos[0]["alt"],
                        "source": photos[0]["source"],
                    })

        # 第三轮：如果还是不够，用通用话题词保底
        if len(images) < 3:
            needed = 3 - len(images)
            fallback_keywords = TOPIC_KEYWORDS_MAP["默认"]
            for kw in fallback_keywords[:needed]:
                photos = self.searcher.search(kw, per_page=2)
                if photos:
                    images.append({
                        "paragraph_index": len(images),
                        "keywords": kw,
                        "url": photos[0]["url"],
                        "thumb_url": photos[0]["thumb_url"],
                        "alt": photos[0]["alt"],
                        "source": photos[0]["source"],
                    })

        article["images"] = images
        logger.info(f"配图: {title[:20]}... → {len(images)} 张")
        return article

    def _extract_keywords(self, title: str) -> list:
        """从标题中提取搜索关键词（中文+英文组合）

        策略：
        1. 尝试识别话题类别，用对应的通用英文词
        2. 提取标题中的核心名词
        3. 用更宽泛的词，确保能搜到图
        """
        keywords = []

        # 简单的关键词映射（标题中包含某个词 → 推荐搜索词）
        keyword_map = [
            ("钓鱼", ["fishing", "lake", "fish"]),
            ("鱼", ["fish", "fishing", "ocean"]),
            ("消费", ["shopping", "market", "money"]),
            ("旅游", ["travel", "airplane", "tourist"]),
            ("酒店", ["hotel", "travel", "vacation"]),
            ("航班", ["airplane", "airport", "travel"]),
            ("飞机", ["airplane", "flight", "airport"]),
            ("救援", ["rescue", "emergency", "firefighter"]),
            ("安全", ["safety", "shield", "protection"]),
            ("教育", ["education", "school", "student"]),
            ("学生", ["student", "school", "education"]),
            ("班额", ["classroom", "school", "education"]),
            ("班级", ["classroom", "school", "student"]),
            ("口岸", ["border", "truck", "road"]),
            ("边疆", ["mountain", "border", "landscape"]),
            ("基础设施", ["construction", "building", "road"]),
            ("酒后", ["alcohol", "glass", "warning"]),
            ("跳河", ["river", "water", "emergency"]),
            ("失联", ["searching", "fog", "mystery"]),
            ("家庭", ["family", "home", "people"]),
            ("旅行", ["travel", "vacation", "beach"]),
            ("英国", ["london", "uk flag", "big ben"]),
            ("俄罗斯", ["moscow", "kremlin", "russia"]),
            ("关系", ["handshake", "meeting", "business people"]),
            ("市场", ["market", "shopping", "business"]),
            ("趋势", ["graph", "trend", "chart"]),
            ("暑期", ["summer", "beach", "vacation"]),
            ("悲剧", ["sad", "rain", "dark clouds"]),
            ("争议", ["debate", "meeting", "discussion"]),
            ("超标", ["warning", "alert", "chart"]),
            ("初中", ["school", "student", "classroom"]),
            ("规模", ["building", "city", "architecture"]),
            ("问题", ["question", "thinking", "confused"]),
            ("发展", ["growth", "progress", "city"]),
        ]

        for keyword, search_terms in keyword_map:
            if keyword in title:
                keywords.extend(search_terms)
                break  # 只匹配第一个

        # 如果没匹配到，用通用词
        if not keywords:
            keywords = ["news", "city", "people"]

        return keywords[:5]

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
            # 降级：返回空，让外层走兜底搜索
            return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from images.search_api import ImageSearcher
    searcher = ImageSearcher()
    matcher = ImageMatcher(searcher)
    test_article = {"main_title": "AI技术", "summary": "AI", "content": "段落1\n段落2"}
    result = matcher._match_one(test_article)
    print(json.dumps(result, ensure_ascii=False, indent=2))
