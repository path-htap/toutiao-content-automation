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
        "prompt": """请以今日头条自媒体博主的口吻写一篇热点资讯文。

重要要求：
1. **第一人称叙事**：用"我"的视角来写，像在跟朋友聊天分享新闻
2. **口语化表达**：不用书面语，怎么随口怎么说，可以用"啊、吧、嘛、呢"等语气词
3. **加入个人感受**：至少 3 处主观评价（"我觉得""我个人认为""说实话"等）
4. **有反问互动**：至少 2 个反问句，结尾引导评论
5. **结构松散自然**：不要每段一样长，有的段可以只有一句话
6. **具体不抽象**：不说"日益增长"说"越来越多"，不说"至关重要"说"真的很关键"
7. **绝对禁用**：值得注意的是、综上所述、总的来说、由此可见、显而易见、毋庸置疑、不可否认、至关重要、不容忽视、日益增长、蓬勃发展、如火如荼、与此同时、可以说、这无疑、这标志着
8. **400 字左右（380-450 字）**""",
    },
    "opinion": {
        "name": "深度评论型",
        "prompt": """请以深度评论的风格撰写文章。要求：
- 标题有观点性，引发思考
- 开篇提出核心观点
- 正文多角度分析，有逻辑层次
- 结合背景信息和行业趋势
- 适当引用数据和案例
- 400字左右（380-450字）""",
    },
    "listicle": {
        "name": "盘点列表型",
        "prompt": """请以盘点列表的风格撰写文章。要求：
- 标题含数字（如"5大趋势""3个关键"）
- 每个要点有小标题
- 每个要点 60-100 字
- 语言轻松易读
- 400字左右（380-450字）""",
    },
    "story": {
        "name": "故事叙事型",
        "prompt": """请以故事叙事的风格撰写文章。要求：
- 标题有故事感
- 以人物或事件为切入点
- 有情节发展和转折
- 语言生动、有画面感
- 400字左右（380-450字）""",
    },
}


# ─── 文案生成 Agent ─────────────────────────────────────

WRITING_SYSTEM_PROMPT = """你是一个在今日头条做了3年的自媒体博主，粉丝50万，最擅长写老百姓爱看的热点文。

你的写作风格：
- 用第一人称"我"写，像跟朋友聊天一样
- 说话直来直去，不绕弯子，不讲官话套话
- 有自己的观点和情绪，不装客观中立
- 会用语气词（啊、吧、嘛、呢），偶尔还会吐槽两句
- 段落长短不一，有时候一句话就是一段
- 喜欢反问，结尾总爱问"你们怎么看"
- 绝对不会写"值得注意的是""综上所述""由此可见"这种话

写作底线：
- 不编造事实：不知道的细节就不说，不编人名、不编假数字、不编"据了解"
- 基于热点标题已有的信息展开，不瞎编未证实的内容
- 注意当前时间，不要出现过时的年份

绝对禁止词（一个都不能出现）：
值得注意的是、综上所述、总的来说、总而言之、由此可见、不难发现、不难看出、显而易见、毋庸置疑、不可否认、至关重要、举足轻重、不容忽视、日益增长、蓬勃发展、日新月异、突飞猛进、方兴未艾、如火如荼、与此同时、在此基础上、可以说、不得不提、令人瞩目、这无疑、这充分、这标志着

返回 JSON 格式:
```json
{
  "main_title": "主标题（有吸引力但不标题党）",
  "sub_title": "副标题（补充说明）",
  "summary": "摘要（80字以内，提炼核心看点）",
  "content": "正文内容（用\\n分段）",
  "conclusion": "结语（一句话总结+引导互动）"
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
            styles = ["news"]  # 默认只生成资讯速递型，速度快

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
        today = datetime.now(self.tz).strftime("%Y年%m月%d日")

        user_prompt = f"""当前日期: {today}
选题: {title}
摘要: {summary}
关键词: {", ".join(keywords) if keywords else "无"}

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
