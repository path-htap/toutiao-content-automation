"""去 AI 味重写模块（加强版）

核心策略：不是"润色"，而是"用口语重新讲一遍"。
三层处理 → 五层处理，每一层都更激进：
  Tier 1: 词汇层 - 替换 AI 套话
  Tier 2: 句式层 - 打破工整结构，长短句交替
  Tier 3: 视角层 - 加入第一人称、个人感受、反问
  Tier 4: 细节层 - 增加具体细节、口语助词、语气词
  Tier 5: 整体重写 - LLM 用"聊天口吻"重新讲一遍

参考: Humanizer-zh / shuorenhua / GPTZero 绕过策略
"""

import json
import logging
import random
import re

from humanizer.patterns import PatternDetector

logger = logging.getLogger(__name__)

# ─── 深度去AI味 Prompt（极端版） ──────────────────────

DEEP_HUMANIZE_PROMPT = """你现在要扮演一个今日头条的普通读者，用你平时刷手机时说话的方式，把下面这篇文章"用自己的话"重新讲一遍。

## 核心原则（必须严格遵守）

1. **绝对不要用书面语**：就像跟朋友聊天一样，怎么随口怎么来
2. **必须加第一人称**：至少出现 3 次"我觉得""我个人认为""说实话""你别说"之类的主观表达
3. **要有"不完美"**：可以有语气词（啊、吧、嘛、呢、哎）、可以有重复、可以有"废话"
4. **打破工整结构**：不要每段长度差不多，有的段就一句话也行
5. **加入反问和设问**：至少加 1-2 个反问句（比如"你说是不是？""换作是你呢？"）
6. **用具体代替抽象**：不要说"日益增长"，说"越来越多了"；不要说"至关重要"，说"真的很关键"
7. **增加口语连接**：用"话说回来""你别说""讲真""实不相瞒""有意思的是"代替"综上所述""值得注意的是"
8. **结尾要互动**：最后加一句引导评论的话，比如"你们怎么看？评论区聊聊""换作是你你会怎么做？"

## 绝对禁止出现的词（一个都不能有）

值得注意的是、综上所述、总的来说、总而言之、由此可见、不难发现、不难看出、显而易见、毋庸置疑、不可否认、至关重要、举足轻重、不容忽视、日益增长、蓬勃发展、日新月异、突飞猛进、方兴未艾、如火如荼、与此同时、在此基础上、作为重要组成部分、在这样的背景下、随着时代的发展、扮演着重要角色、发挥着重要作用、具有重要意义、可以说、不得不提、令人瞩目、这无疑、这充分、这标志着

## 输出要求

- 只输出重写后的正文，不要标题、不要摘要、不要任何解释
- 段落之间用空行分隔
- 字数跟原文差不多就行（±20%都可以接受）
- 核心事实信息不能变，但表达方式必须完全不一样
- 允许加入合理的个人评论和感受

---

原文：
{content}

---

请用聊天口吻重新讲一遍："""


# ─── 口语化词库 ─────────────────────────────────────────

# 书面语 → 口语替换表（更彻底）
FORMAL_TO_CASUAL = {
    "值得注意的是": "有意思的是",
    "综上所述": "说到底",
    "总的来说": "整体看下来",
    "总而言之": "一句话",
    "由此可见": "看得出来",
    "不难发现": "你会发现",
    "不难看出": "很明显",
    "显而易见": "明眼人都能看出来",
    "毋庸置疑": "这个不用多说",
    "不可否认": "说句公道话",
    "至关重要": "最关键的是",
    "举足轻重": "地位挺高的",
    "不容忽视": "可不能小看",
    "日益增长": "越来越多",
    "蓬勃发展": "发展得红红火火",
    "日新月异": "一天一个样",
    "突飞猛进": "进步神速",
    "方兴未艾": "势头正猛",
    "如火如荼": "热火朝天",
    "与此同时": "另一边",
    "在此基础上": "在这个前提下",
    "可以说": "",
    "不得不提": "还有一点",
    "令人瞩目": "挺让人关注的",
    "这无疑": "这绝对是",
    "这充分": "这",
    "这标志着": "意味着",
    "众所周知": "大家都知道",
    "据了解": "听说",
    "据悉": "据说",
    "据报道": "看到消息说",
    "相关部门": "有关方面",
    "相关人员": "相关的人",
    "进行了": "做了",
    "开展了": "搞了",
    "实施了": "推了",
    "实现了": "做到了",
    "取得了": "拿到了",
    "给予了": "给了",
    "提供了": "给了",
}

# 句首语气词（随机插入，增加口语感）
SENTENCE_STARTERS = [
    "说实话，",
    "讲真，",
    "你别说，",
    "实不相瞒，",
    "我觉得吧，",
    "个人感觉，",
    "有意思的是，",
    "话说回来，",
    "你还别说，",
    "在我看来，",
    "我个人认为，",
]

# 句末语气词（随机加在陈述句末尾）
SENTENCE_ENDERS = ["啊", "吧", "嘛", "呢", "哦", "哈"]

# 过渡句（用来打破段落间的工整连接）
TRANSITIONS = [
    "说起来也是有意思。",
    "你猜怎么着？",
    "这事儿吧，说复杂也复杂，说简单也简单。",
    "换个角度想，其实也能理解。",
    "我看到这个新闻的时候第一反应就是：这也行？",
    "不得不说，还是挺让人意外的。",
    "具体怎么回事呢？听我慢慢说。",
    "当然了，每个人看法不一样。",
]


class Humanizer:
    """去 AI 味处理器（加强版）"""

    def __init__(self):
        self.detector = PatternDetector()
        self._rng = random.Random(42)  # 固定种子，保证可复现

    def process(self, articles: list) -> list:
        """对文章列表进行去 AI 味处理"""
        results = []
        for article in articles:
            processed = self._process_one(article)
            results.append(processed)

        logger.info(f"去AI味完成: {len(results)} 篇")
        return results

    def _process_one(self, article: dict) -> dict:
        """处理单篇文章（5 层深度处理）"""
        content = article.get("content", "")
        title = article.get("main_title", "")

        # 处理前检测
        before_report = self.detector.detect(content)

        # Tier 1: 词汇层 - 批量替换 AI 套话
        content = self._tier1_replace(content)

        # Tier 2: 句式层 - 打破工整结构
        content = self._tier2_sentence_mix(content)

        # Tier 3: 视角层 - 加入第一人称和主观感受
        content = self._tier3_perspective(content)

        # Tier 4: 细节层 - 加入语气词、口语助词
        content = self._tier4_details(content)

        # Tier 5: LLM 深度重写（核心步骤，用口语重新讲一遍）
        content = self._tier5_deep_rewrite(content, title)

        # 处理后检测
        after_report = self.detector.detect(content)

        # 更新文章
        article["content"] = content
        article["humanizer_report"] = {
            "before_ai_score": before_report["ai_score"],
            "after_ai_score": after_report["ai_score"],
            "score_reduction": before_report["ai_score"] - after_report["ai_score"],
            "tiers_applied": 5,
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
        """Tier 1: 词汇层 - 批量替换 AI 高频词和套话"""
        for formal, casual in FORMAL_TO_CASUAL.items():
            if formal in content:
                content = content.replace(formal, casual)
        return content

    def _tier2_sentence_mix(self, content: str) -> str:
        """Tier 2: 句式层 - 打破工整结构，长短句交替

        策略：
        - 把一些长句拆成短句
        - 偶尔把独立句子单独成段
        - 加入设问句
        """
        paragraphs = [p for p in content.split("\n") if p.strip()]
        result = []

        for i, para in enumerate(paragraphs):
            # 每 3 段拆一段：把一个长段落拆成两段
            if i % 3 == 1 and len(para) > 100:
                # 找一个中间位置的句号、逗号或问号拆开
                mid = len(para) // 2
                split_pos = -1
                for sep in ["。", "！", "？", "，", "；"]:
                    pos = para.find(sep, mid - 20, mid + 20)
                    if pos != -1:
                        split_pos = pos + 1
                        break

                if split_pos > 0:
                    first_half = para[:split_pos].strip()
                    second_half = para[split_pos:].strip()
                    result.append(first_half)
                    # 第二段前加一句过渡
                    if i % 2 == 0:
                        result.append("你猜后续怎么着？")
                    result.append(second_half)
                else:
                    result.append(para)
            else:
                result.append(para)

        return "\n\n".join(result)

    def _tier3_perspective(self, content: str) -> str:
        """Tier 3: 视角层 - 加入第一人称和主观感受

        策略：
        - 在 2-3 个句子前加入第一人称开头
        - 加入反问句
        - 加入个人评价
        """
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        result = []

        for i, para in enumerate(paragraphs):
            modified = para

            # 第 1 段加入"我看到"开头的引入
            if i == 0 and not para.startswith(("我", "你", "说", "讲")):
                modified = "我刷到这个消息的时候，第一反应是——" + modified

            # 中间段落随机加入第一人称评价
            elif i > 0 and i < len(paragraphs) - 1 and len(para) > 50:
                # 在段落末尾加入个人评论
                if self._rng.random() > 0.5:
                    opinions = [
                        "我个人觉得吧，这事儿还真没那么简单。",
                        "你别说，仔细想想还挺有道理的。",
                        "说实话，我是觉得挺意外的。",
                        "在我看来，这还只是开始。",
                        "换作是我的话，可能也会这么做。",
                    ]
                    opinion = self._rng.choice(opinions)
                    modified = modified.rstrip("。！？") + "。" + opinion
                else:
                    # 在段首加入过渡
                    starter = self._rng.choice(SENTENCE_STARTERS)
                    if not modified.startswith(tuple(SENTENCE_STARTERS)):
                        modified = starter + modified

            # 最后一段加入反问互动
            if i == len(paragraphs) - 1:
                questions = [
                    "你们怎么看？评论区聊聊。",
                    "换作是你，你会怎么做？",
                    "这事儿吧，我觉得还得再观察观察，你们说呢？",
                    "不知道大家有没有同感？",
                ]
                question = self._rng.choice(questions)
                modified = modified.rstrip("。！？") + "。" + question

            result.append(modified)

        return "\n\n".join(result)

    def _tier4_details(self, content: str) -> str:
        """Tier 4: 细节层 - 加入语气词和口语细节

        策略：
        - 少量句子末尾加语气词（啊、吧、嘛）
        - 加入一些"废话"连接
        - 让文字更"碎"一点
        """
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        result = []

        for para in paragraphs:
            sentences = re.split(r"([。！？])", para)
            new_sentences = []

            for j in range(0, len(sentences) - 1, 2):
                sent = sentences[j]
                punct = sentences[j + 1] if j + 1 < len(sentences) else "。"

                # 大约 20% 的句子加句末语气词
                if self._rng.random() < 0.2 and len(sent) > 10 and punct == "。":
                    ender = self._rng.choice(SENTENCE_ENDERS)
                    # 避免重复
                    if not sent.endswith(tuple(SENTENCE_ENDERS)):
                        sent = sent + ender

                new_sentences.append(sent + punct)

            result.append("".join(new_sentences))

        return "\n\n".join(result)

    def _tier5_deep_rewrite(self, content: str, title: str) -> str:
        """Tier 5: LLM 深度重写（核心步骤）

        让 LLM 用"聊天口吻"把文章重新讲一遍，
        这是最有效的去 AI 味手段。
        """
        from writers.article_agent import LLMClient

        try:
            client = LLMClient()
            prompt = DEEP_HUMANIZE_PROMPT.format(content=content)
            response = client.chat([
                {"role": "system", "content": "你是一个说话接地气的普通网民，平时最爱刷今日头条，说话直来直去，从不讲套话。"},
                {"role": "user", "content": prompt}
            ], temperature=0.9)  # 高 temperature，增加随机性

            rewritten = response.choices[0].message.content.strip()

            # 清理可能的 markdown 标记
            rewritten = re.sub(r"^#+\s*", "", rewritten, flags=re.MULTILINE)

            if rewritten and len(rewritten) > 200:  # 确保重写有效
                logger.info(f"Tier 5 深度重写完成: {len(content)}字 → {len(rewritten)}字")
                return rewritten
            else:
                logger.warning("Tier 5 重写结果太短，使用上一版本")
                return content

        except Exception as e:
            logger.error(f"Tier 5 深度重写失败: {e}")
            return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    humanizer = Humanizer()
    test_article = {
        "main_title": "测试",
        "content": "值得注意的是，AI技术日益增长。综上所述，这至关重要。随着人工智能的蓬勃发展，其在各个领域发挥着举足轻重的作用。",
    }
    result = humanizer._process_one(test_article)
    print("原文:")
    print(test_article["content"])
    print("\n重写后:")
    print(result["content"])
    print("\n报告:")
    print(json.dumps(result.get("humanizer_report", {}), ensure_ascii=False, indent=2))
