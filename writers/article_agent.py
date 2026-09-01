"""AI 文案撰写模块

调用 LLM（智谱AI GLM-4-Flash）根据选题生成多篇不同风格文案。
支持多种风格: 资讯速递 / 深度评论 / 盘点列表 / 故事叙事
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ─── LLM 客户端 ─────────────────────────────────────────

class LLMClient:
    """统一 LLM 客户端，支持多平台切换

    所有免费 LLM API（智谱AI/硅基流动/Groq等）均兼容 OpenAI 接口格式。
    """

    PROVIDERS = {
        "zhipu": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4/",
            "model": "glm-4-flash",
            "key_env": "ZHIPU_API_KEY"
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "Qwen2.5-7B-Instruct",
            "key_env": "SILICONFLOW_API_KEY"
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "key_env": "GROQ_API_KEY"
        },
    }

    def __init__(self, provider: str = "zhipu"):
        from openai import OpenAI

        # 自动选择有 API Key 的提供商
        if not os.getenv(self.PROVIDERS[provider]["key_env"]):
            for p in self.PROVIDERS:
                if os.getenv(self.PROVIDERS[p]["key_env"]):
                    provider = p
                    break

        config = self.PROVIDERS[provider]
        self.provider = provider
        self.model = config["model"]
        self.client = OpenAI(
            api_key=os.getenv(config["key_env"], ""),
            base_url=config["base_url"]
        )
        logger.info(f"LLM 提供商: {provider}, 模型: {self.model}")

    def chat(self, messages: list, **kwargs) -> object:
        """调用 LLM 对话接口"""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )


# ─── 文案风格模板 ───────────────────────────────────────

STYLE_TEMPLATES = {
    "news": {
        "name": "资讯速递型",
        "prompt": """请以新闻资讯的风格撰写文章。要求：
- 标题简明扼要，突出核心信息
- 导语概括事件（人物、时间、地点、事件）
- 正文按重要性递减排列
- 语言客观、准确、简洁
- 800-1500字""",
    },
    "opinion": {
        "name": "深度评论型",
        "prompt": """请以深度评论的风格撰写文章。要求：
- 标题有观点性，引发思考
- 开篇提出核心观点
- 正文多角度分析，有逻辑层次
- 结合背景信息和行业趋势
- 适当引用数据和案例
- 1500-2000字""",
    },
    "listicle": {
        "name": "盘点列表型",
        "prompt": """请以盘点列表的风格撰写文章。要求：
- 标题含数字（如"5大趋势""3个关键"）
- 每个要点有小标题
- 每个要点 200-300 字
- 语言轻松易读
- 800-1200字""",
    },
    "story": {
        "name": "故事叙事型",
        "prompt": """请以故事叙事的风格撰写文章。要求：
- 标题有故事感
- 以人物或事件为切入点
- 有情节发展和转折
- 语言生动、有画面感
- 1200-1800字""",
    },
}


# ─── 文案生成 Agent ─────────────────────────────────────

WRITING_SYSTEM_PROMPT = """你是一位专业的内容创作者。请根据给定的选题和要求撰写高质量文章。

要求:
1. 生成主标题和副标题
2. 生成摘要（≤100字）
3. 正文至少3个段落
4. 包含结语
5. 内容真实准确，不编造事实
6. 语言自然流畅，避免AI写作痕迹

返回 JSON 格式:
```json
{
  "main_title": "主标题",
  "sub_title": "副标题",
  "summary": "摘要",
  "content": "正文内容（用\\n分段）",
  "conclusion": "结语"
}
```"""


class ArticleAgent:
    """文案生成 Agent"""

    def __init__(self):
        self.tz = timezone(timedelta(hours=8))
        self.client = None

    def _get_client(self) -> LLMClient:
        if self.client is None:
            self.client = LLMClient()
        return self.client

    def generate_articles(self, topics: list, styles: list = None) -> list:
        """为每个选题生成多篇不同风格文案

        Args:
            topics: 选题列表
            styles: 要生成的风格列表，默认 ['news', 'opinion']

        Returns:
            文章列表
        """
        if styles is None:
            styles = ["news", "opinion"]

        articles = []
        client = self._get_client()

        for topic in topics:
            title = topic.get("title", "")
            summary = topic.get("summary", "")
            keywords = topic.get("keywords", [])

            for style in styles:
                template = STYLE_TEMPLATES.get(style, STYLE_TEMPLATES["news"])
                logger.info(f"生成文案: {title} [{template['name']}]")

                article = self._generate_one(client, title, summary, keywords, style)
                if article:
                    article["source_topic"] = title
                    article["style"] = style
                    article["style_name"] = template["name"]
                    articles.append(article)

        logger.info(f"文案生成完成: {len(articles)} 篇")
        return articles

    def _generate_one(self, client: LLMClient, title: str, summary: str,
                      keywords: list, style: str) -> dict:
        """生成单篇文案"""
        template = STYLE_TEMPLATES[style]

        user_prompt = f"""选题: {title}
摘要: {summary}
关键词: {", ".join(keywords)}

{template['prompt']}

请返回 JSON 格式的文章。"""

        try:
            response = client.chat([
                {"role": "system", "content": WRITING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ])
            content = response.choices[0].message.content
            return self._parse_article(content)

        except Exception as e:
            logger.error(f"文案生成失败 [{title}]: {e}")
            return {}

    def _parse_article(self, content: str) -> dict:
        """解析 LLM 返回的文章 JSON"""
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end]
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("文案 JSON 解析失败")
            return {"main_title": "解析失败", "content": content}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ArticleAgent()
    test_topics = [{"title": "测试", "summary": "测试摘要", "keywords": ["测试"]}]
    articles = agent.generate_articles(test_topics)
    print(json.dumps(articles[:1], ensure_ascii=False, indent=2))
