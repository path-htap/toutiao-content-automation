"""去 AI 味重写模块

三层处理：①词汇层 ②语法层 ③思维层
使用规则替换 + LLM 重写相结合。
参考: Humanizer-zh / shuorenhua 项目
"""

import json
import logging

from humanizer.patterns import PatternDetector

logger = logging.getLogger(__name__)

# 去AI味 LLM Prompt
HUMANIZE_PROMPT = """请将以下文章重写为更自然的人类写作风格。

要求:
1. 替换 AI 常用套路表达（"值得注意的是""综上所述"等）为自然口语
2. 句式多样化：长短句交替、适当口语化
3. 加入个人观点和情感色彩（但不过度）
4. 允许轻微的"不完美"（口语化停顿词、省略）
5. 保持核心信息不变（信息覆盖率 ≥ 95%）
6. 保持专业术语不变
7. 字数变化不超过 ±15%

原文:
{content}

返回重写后的文章正文（纯文本，用\\n分段），不要包含标题和摘要。"""


class Humanizer:
    """去 AI 味处理器"""

    def __init__(self):
        self.detector = PatternDetector()

    def process(self, articles: list) -> list:
        """对文章列表进行去 AI 味处理

        Args:
            articles: 文章列表

        Returns:
            处理后的文章列表（添加 humanizer_report 字段）
        """
        results = []
        for article in articles:
            processed = self._process_one(article)
            results.append(processed)

        logger.info(f"去AI味完成: {len(results)} 篇")
        return results

    def _process_one(self, article: dict) -> dict:
        """处理单篇文章"""
        content = article.get("content", "")
        title = article.get("main_title", "")

        # 处理前检测
        before_report = self.detector.detect(content)

        # Tier 1: 词汇层 - 直接替换
        tier1_content = self._tier1_replace(content)

        # Tier 2: 语法层 - LLM 重写（如果 Tier 1 后 AI 味仍重）
        tier2_report = self.detector.detect(tier1_content)
        if tier2_report["ai_score"] > 30:
            tier2_content = self._tier2_rewrite(tier1_content, title)
        else:
            tier2_content = tier1_content

        # Tier 3: 思维层 - 仅在 AI 味极重时触发
        tier3_report = self.detector.detect(tier2_content)
        if tier3_report["ai_score"] > 50:
            tier3_content = self._tier3_inject(tier2_content)
        else:
            tier3_content = tier2_content

        # 处理后检测
        after_report = self.detector.detect(tier3_content)

        # 更新文章
        article["content"] = tier3_content
        article["humanizer_report"] = {
            "before_ai_score": before_report["ai_score"],
            "after_ai_score": after_report["ai_score"],
            "score_reduction": before_report["ai_score"] - after_report["ai_score"],
            "tier1_applied": True,
            "tier2_applied": tier2_report["ai_score"] > 30,
            "tier3_applied": tier3_report["ai_score"] > 50,
            "before_patterns": before_report["pattern_count"],
            "after_patterns": after_report["pattern_count"],
        }

        reduction = before_report["ai_score"] - after_report["ai_score"]
        logger.info(
            f"去AI味 [{title[:20]}]: "
            f"AI分 {before_report['ai_score']}→{after_report['ai_score']} "
            f"(降低 {reduction})"
        )

        return article

    def _tier1_replace(self, content: str) -> str:
        """Tier 1: 词汇层 - 直接替换 AI 高频词"""
        replacements = self.detector.get_replacements(content)
        for rep in replacements:
            original = rep["original"]
            suggestion = rep["suggestion"]
            if suggestion:
                content = content.replace(original, suggestion)
            else:
                content = content.replace(original, "")
        return content

    def _tier2_rewrite(self, content: str, title: str) -> str:
        """Tier 2: 语法层 - LLM 重写"""
        from writers.article_agent import LLMClient

        try:
            client = LLMClient()
            prompt = HUMANIZE_PROMPT.format(content=content)
            response = client.chat([
                {"role": "system", "content": "你是一位文字润色专家，擅长将AI生成的文本改写为自然的人类写作。"},
                {"role": "user", "content": prompt}
            ])
            rewritten = response.choices[0].message.content.strip()
            return rewritten if rewritten else content
        except Exception as e:
            logger.error(f"Tier 2 重写失败: {e}")
            return content

    def _tier3_inject(self, content: str) -> str:
        """Tier 3: 思维层 - 注入个人观点和跳跃性

        简化实现：在段落间插入过渡思考。
        生产环境可调 LLM 生成个人化观点。
        """
        # 简化: 在段落间加入思考连接词
        transitions = ["说实在的，", "换个角度看，", "仔细想想，"]
        paragraphs = content.split("\n")
        if len(paragraphs) > 2:
            idx = len(paragraphs) // 2
            transition = transitions[len(paragraphs) % len(transitions)]
            if not paragraphs[idx].startswith(tuple(transitions)):
                paragraphs[idx] = transition + paragraphs[idx]
        return "\n".join(paragraphs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    humanizer = Humanizer()
    test_article = {
        "main_title": "测试",
        "content": "值得注意的是，AI技术日益增长。综上所述，这至关重要。",
    }
    result = humanizer._process_one(test_article)
    print(json.dumps(result.get("humanizer_report", {}), ensure_ascii=False, indent=2))
