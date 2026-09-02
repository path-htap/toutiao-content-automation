"""去 AI 味重写模块（加强版 v2）

核心策略：不是"润色"，而是"用口语重新讲一遍"。
在原有 5 层处理基础上，并入 Humanizer-zh 的中文写作模式，
更系统地清除：欧化翻译腔、破折号滥用、排比对仗、系动词回避、
虚假互动结尾、AI 高频词、以及"假坦诚"开场等痕迹。

层级（v2）：
  Tier 1: 词汇层 - 替换 AI 套话 / 互联网黑话 / 翻译腔（扩充词库）
  Tier 2: 句式层 - 打破工整结构，长短句交替
  Tier 3: 视角层 - 加入第一人称、个人感受、反问
  Tier 4: 细节层 - 增加具体细节、口语助词、语气词
  Tier 4.5: 标点与排版层 - 清理破折号滥用、排比堆砌、加粗/emoji 装饰、虚假互动
  Tier 5: 整体重写 - LLM 用"聊天口吻"重新讲一遍
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
9. **说人话，不要端**：不要像新闻稿，要像刷短视频时随手写的评论。可以用一个真实的反应、一个具体的场景开头
10. **可以有倾向**：不要骑墙；实在拿不准就给出你的判断和理由

## 绝对禁止出现的词（一个都不能有）

值得注意的是、综上所述、总的来说、总而言之、由此可见、不难发现、不难看出、显而易见、毋庸置疑、不可否认、至关重要、举足轻重、不容忽视、日益增长、蓬勃发展、日新月异、突飞猛进、方兴未艾、如火如荼、与此同时、在此基础上、作为重要组成部分、在这样的背景下、随着时代的发展、扮演着重要角色、发挥着重要作用、具有重要意义、可以说、不得不提、令人瞩目、这无疑、这充分、这标志着、标志着、见证了、象征着、彰显了、凸显了、意味着一个、作为……的体现、为……奠定基础、不断演变的格局、不可磨灭的印记、深度融合、协同发力、赋能、抓手、闭环、底层逻辑、颗粒度、组合拳、出拳、引爆、抢跑、赛道、天花板、红利期、风口、破局、深化落地、打造新高地、谱写新篇章、注入新动能

## 结构禁忌（严格遵守）

- **不要用破折号当"转折/强调"**（X——Y），改成逗号或句号
- **不要三连排比、不要"不仅是…更是…""不是…而是…"堆砌**，一篇最多一处
- **不要"作为…""拥有…""标志着…"这种系动词替代**，直接用"是/有"
- **不要"首先…其次…最后…综上"**；不要"话不多说，以下是你需要知道的"这类路标句
- **不要加粗列点、不要 emoji 当分隔**（🚀✅💡），用文字表达层次
- **不要"你觉得呢？点赞关注~"这样的假互动**，具体指出你真正想问的问题

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

# 书面语 → 口语替换表（更彻底；并入 Humanizer-zh / 中文社区共识）
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
    "发挥了重要作用": "帮了大忙",
    "扮演着重要角色": "挺关键的",
    "具有重要意义": "意义挺大",
    "作为重要组成部分": "是很重要的一块",
    "随着时代的发展": "这几年",
    "在这样的背景下": "在这种情况里",
    "作为": "是",
    "标志着": "说明",
    "见证了": "赶上了",
    "象征着": "就是",
    "彰显了": "看得出",
    "凸显了": "显出",
    "意味着一个": "那就是",
    "深度融合": "彻底绑到一起",
    "协同发力": "一起使劲",
    "赋能": "帮上忙",
    "抓手": "抓手",
    "闭环": "能转起来",
    "底层逻辑": "根本道理",
    "颗粒度": "细到什么程度",
    "引爆": "带火",
    "抢跑": "抢先",
    "风口": "热门",
    "破局": "打开局面",
    "谱写新篇章": "上个大台阶",
    "注入新动能": "供上有劲的新东西",
    "打造新高地": "做出个新高度",
    "至关重要": "特重要",
    "不容小觑": "可别小看",
    # 人文/宣传性语言
    "令人叹为观止": "绝了",
    "必游之地": "一定要去看看",
    "充满活力": "特别有劲",
    "丰富的文化遗产": "文化底蕴挺厚",
    "迷人的": "很吸引人",
    "坐落于": "在",
    "位于": "在",
    "致力于": "一心扑在",
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
    "说实话，这事儿吧，",
]

# 句末语气词（随机加在陈述句末尾）
SENTENCE_ENDERS = ["啊", "吧", "嘛", "呢", "哦", "哈"]

# 过渡句（用来打破段落间的工整连接）
TRANSITIONS = [
    "说起来也是有意思。",
    "你猜怎么着，",
    "反正我是没想到。",
    "这事儿吧，说复杂也复杂，说简单也简单。",
    "换个角度想，其实也能理解。",
    "我看到这个新闻的时候第一反应就是：这也行？",
    "不得不说，还是挺让人意外的。",
    "具体怎么回事呢？听我慢慢说。",
    "当然了，每个人看法不一样。",
]


class Humanizer:
    """去 AI 味处理器（加强版 v2）"""

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

        # Tier 4.5: 标点与排版层 - 清理破折号滥用/排比/虚假互动/emoji
        content = self._tier45_markup_clean(content)

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
            "tiers_applied": 6,
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
        """Tier 2: 句式层 - 打破工整结构，长短句交替"""
        paragraphs = [p for p in content.split("\n") if p.strip()]
        result = []

        for i, para in enumerate(paragraphs):
            if i % 3 == 1 and len(para) > 100:
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
                    if i % 2 == 0:
                        result.append("你猜后续怎么着？")
                    result.append(second_half)
                else:
                    result.append(para)
            else:
                result.append(para)

        return "\n\n".join(result)

    def _tier3_perspective(self, content: str) -> str:
        """Tier 3: 视角层 - 加入第一人称和主观感受"""
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        result = []

        for i, para in enumerate(paragraphs):
            modified = para

            if i == 0 and not para.startswith(("我", "你", "说", "讲")):
                modified = "我刷到这个消息的时候，第一反应是——" + modified

            elif i > 0 and i < len(paragraphs) - 1 and len(para) > 50:
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
                    starter = self._rng.choice(SENTENCE_STARTERS)
                    if not modified.startswith(tuple(SENTENCE_STARTERS)):
                        modified = starter + modified

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
        """Tier 4: 细节层 - 加入语气词和口语细节"""
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        result = []

        for para in paragraphs:
            sentences = re.split(r"([。！？])", para)
            new_sentences = []

            for j in range(0, len(sentences) - 1, 2):
                sent = sentences[j]
                punct = sentences[j + 1] if j + 1 < len(sentences) else "。"

                if self._rng.random() < 0.2 and len(sent) > 10 and punct == "。":
                    ender = self._rng.choice(SENTENCE_ENDERS)
                    if not sent.endswith(tuple(SENTENCE_ENDERS)):
                        sent = sent + ender

                new_sentences.append(sent + punct)

            result.append("".join(new_sentences))

        return "\n\n".join(result)

    def _tier45_markup_clean(self, content: str) -> str:
        """Tier 4.5: 标点与排版层（新增）

        清理 Humanizer-zh 识别的"标点与排版 / 结构"类 AI 痕迹：
        - 破折号滥用：把 "X——Y" 简化，只保留真正需要的
        - 三连排比 / 对仗堆砌：适当合并
        - 加粗列点、emoji 装饰：转成普通文字
        - 路标句（"首先…其次…"）、公式化小标题
        - "不仅是…更是…""不是…而是…"：保留，但只留一处（此处简化处理）
        - 虚假互动结尾：删掉纯引流式的"你觉得呢？点赞关注"
        """
        # 1) emoji 装饰符号（🚀✅💡🔥⭐）直接去掉，避免被当"结构痕迹"
        #    注意：re 不支持 \u{HEX} 花括号形式（那是 JS/PCRE 语法），只能用 \uXXXX / \UXXXXXXXX
        content = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", content)

        # 2) 破折号滥用：把大段 "——" 降级为逗号/句号
        #    保留单字破折号用于插入语，但替换 "……——X" 为 "：X"
        content = re.sub(r"([。！？])\s*——\s*", r"\1", content)
        content = re.sub(r"，\s*——\s*", "，", content)
        #    无前导标点：把 "文字——文字" 中间的破折号换成逗号（Tier5 也会兜底，这里再收紧）
        content = re.sub(r"([\u4e00-\u9fffA-Za-z0-9])\s*——\s*((?!——).)", r"\1，\2", content)
        content = re.sub(r"——\s*", "，", content)

        # 3) 路标句：删除 "首先/其次/最后/综上" 类硬编号
        content = re.sub(r"^(首先|其次|再次|最后|综上|另外)[,，、:：]\s*", "", content)

        # 4) 假互动/引流结尾（删除纯引流句，保留真正反问）
        content = re.sub(r"[（(]?(觉得有帮助|有帮助的话|喜欢的话|记得|欢迎|可以点个)[^。！？]{0,20}?(点赞|关注|收藏|转发)[^。！？]*[。！？]?", "", content)
        content = re.sub(r"(点个赞|关注一下|关注哦|记得关注|来个三连|送你小心心)[。！？\s]*", "", content)

        return content

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
