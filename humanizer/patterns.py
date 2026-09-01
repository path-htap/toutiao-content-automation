"""AI 写作模式检测（增强版）

识别 60+ 种 AI 写作高频模式和套路化表达。
参考: Humanizer-zh / shuorenhua / 多种 AI 检测工具特征分析
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# ============================================================
# 一级 AI 特征（权重高，命中即严重扣分）
# ============================================================
AI_PATTERNS_HIGH = [
    # 典型 AI 过渡词（公文/学术腔）
    r"值得注意的是",
    r"综上所述",
    r"总的来说",
    r"总而言之",
    r"由此可见",
    r"不难发现",
    r"不难看出",
    r"显而易见",
    r"毋庸置疑",
    r"不可否认",
    r"不容小觑",
    r"值得一提的是",
    r"值得关注的是",
    r"令人瞩目的是",
    # 空洞形容词堆砌
    r"至关重要",
    r"举足轻重",
    r"不容忽视",
    r"日益增长",
    r"蓬勃发展",
    r"日新月异",
    r"突飞猛进",
    r"方兴未艾",
    r"如火如荼",
    r"欣欣向荣",
    # AI 特征句式
    r"作为.*的重要组成部分",
    r"在.*的大背景下",
    r"随着.*的不断发展",
    r".*扮演着.*角色",
    r".*发挥着.*作用",
    r".*具有重要的.*意义",
    r"为.*提供了有力支撑",
    r"这无疑是",
    r"这充分说明",
    r"这标志着",
    r"可以说",
    r"不得不说",
    r"不得不提",
]

# ============================================================
# 二级 AI 特征（权重中，命中较多也扣分）
# ============================================================
AI_PATTERNS_MEDIUM = [
    r"与此同时",
    r"在此基础上",
    r"从这个角度来看",
    r"从某种意义上说",
    r"在这样的情况下",
    r"更重要的是",
    r"更为关键的是",
    r"进一步来说",
    r"具体而言",
    r"简而言之",
    r"也就是说",
    r"事实证明",
    r"数据显示",
    r"据了解",
    r"据悉",
    r"据报道",
    r"相关数据表明",
    r"业内人士表示",
    r"专家指出",
    r"分析认为",
    r"有效提升",
    r"显著提高",
    r"大幅改善",
    r"积极推动",
    r"全面推进",
    r"深入开展",
    r"不断加强",
    r"持续优化",
]

# ============================================================
# 三级 AI 特征（权重低，辅助判断）
# ============================================================
AI_PATTERNS_LOW = [
    r"首先.*其次.*最后",
    r"一方面.*另一方面",
    r"不仅如此",
    r"除此之外",
    r"除此以外",
    r"更有甚者",
    r"尤其值得",
    r"特别需要",
    r"需要注意的是",
    r"重要的是",
    r"关键在于",
    r"核心是",
    r"本质上",
    r"实际上",
    r"事实上",
    r"基本上",
    r"总体上",
    r"整体来看",
    r"综合来看",
    r"客观来说",
    r"公正地说",
    r"平心而论",
]

# ============================================================
# AI 高频实词（每命中一次加少量分）
# ============================================================
AI_FREQUENCY_WORDS = [
    "赋能", "助力", "聚焦", "打造", "构建", "实现", "推动",
    "促进", "优化", "提升", "改善", "加强", "深化", "拓展",
    "创新", "转型", "升级", "变革", "突破", "跨越", "迈进",
    "高效", "精准", "智能", "智慧", "数字", "生态", "闭环",
    "链路", "抓手", "顶层", "底层", "逻辑", "维度", "层面",
    "格局", "态势", "趋势", "方向", "路径", "模式", "机制",
    "体系", "能力", "水平", "质量", "效益", "成果", "成效",
]


class PatternDetector:
    """AI 写作模式检测器（增强版）"""

    def __init__(self):
        self.patterns_high = [re.compile(p) for p in AI_PATTERNS_HIGH]
        self.patterns_medium = [re.compile(p) for p in AI_PATTERNS_MEDIUM]
        self.patterns_low = [re.compile(p) for p in AI_PATTERNS_LOW]
        self.freq_words = AI_FREQUENCY_WORDS

    def detect(self, text: str) -> dict:
        """检测文本中的 AI 写作模式

        Args:
            text: 待检测文本

        Returns:
            检测结果: {ai_score, details, patterns_found, ...}
            ai_score: 0-100，越低越像人写的
        """
        text_len = max(len(text), 100)  # 避免太短的文本分数失真

        # 1. 一级模式（每个 4 分，上限 40 分）
        high_matches = []
        high_score = 0
        for i, pattern in enumerate(self.patterns_high):
            found = pattern.findall(text)
            if found:
                high_matches.append({
                    "pattern": AI_PATTERNS_HIGH[i],
                    "count": len(found),
                    "level": "high"
                })
                high_score += len(found) * 4
        high_score = min(high_score, 40)

        # 2. 二级模式（每个 2 分，上限 30 分）
        medium_matches = []
        medium_score = 0
        for i, pattern in enumerate(self.patterns_medium):
            found = pattern.findall(text)
            if found:
                medium_matches.append({
                    "pattern": AI_PATTERNS_MEDIUM[i],
                    "count": len(found),
                    "level": "medium"
                })
                medium_score += len(found) * 2
        medium_score = min(medium_score, 30)

        # 3. 三级模式（每个 1 分，上限 15 分）
        low_matches = []
        low_score = 0
        for i, pattern in enumerate(self.patterns_low):
            found = pattern.findall(text)
            if found:
                low_matches.append({
                    "pattern": AI_PATTERNS_LOW[i],
                    "count": len(found),
                    "level": "low"
                })
                low_score += len(found) * 1
        low_score = min(low_score, 15)

        # 4. 高频词（每个 0.5 分，上限 15 分）
        freq_hits = {}
        freq_score = 0
        for word in self.freq_words:
            count = text.count(word)
            if count > 0:
                freq_hits[word] = count
                freq_score += count * 0.5
        freq_score = min(freq_score, 15)

        # 5. 附加特征检测
        bonus_score = 0

        # 段落长度太均匀（AI 写作特征）
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if len(paragraphs) >= 3:
            para_lens = [len(p) for p in paragraphs]
            avg_len = sum(para_lens) / len(para_lens)
            # 计算变异系数（标准差/均值）
            if avg_len > 0:
                variance = sum((l - avg_len) ** 2 for l in para_lens) / len(para_lens)
                std_dev = variance ** 0.5
                cv = std_dev / avg_len
                if cv < 0.2:  # 段落长度非常均匀
                    bonus_score += 5

        # 句子长度太均匀
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) >= 5:
            sent_lens = [len(s) for s in sentences]
            avg_sent_len = sum(sent_lens) / len(sent_lens)
            if avg_sent_len > 0:
                variance = sum((l - avg_sent_len) ** 2 for l in sent_lens) / len(sent_lens)
                std_dev = variance ** 0.5
                cv = std_dev / avg_sent_len
                if cv < 0.25:  # 句子长度非常均匀
                    bonus_score += 5

        # 总分
        ai_score = high_score + medium_score + low_score + freq_score + bonus_score
        ai_score = min(ai_score, 100)  # 上限 100

        all_patterns = high_matches + medium_matches + low_matches

        return {
            "ai_score": ai_score,
            "high_score": high_score,
            "medium_score": medium_score,
            "low_score": low_score,
            "freq_score": freq_score,
            "bonus_score": bonus_score,
            "pattern_count": len(all_patterns),
            "freq_word_count": sum(freq_hits.values()),
            "patterns_found": all_patterns[:15],  # 只返回前 15 个
            "freq_words": dict(list(freq_hits.items())[:10]),
            "paragraph_count": len(paragraphs),
            "details": (
                f"AI模式分 {ai_score:.0f} "
                f"(一级{high_score:.0f}+二级{medium_score:.0f}"
                f"+三级{low_score:.0f}+高频词{freq_score:.0f}"
                f"+结构{bonus_score:.0f})"
            ),
        }

    def get_replacements(self, text: str) -> list:
        """获取需要替换的 AI 模式和建议替换词"""
        replacements = []

        replace_map = {
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
            "这无疑": "这绝对是",
            "值得关注的是": "有意思的是",
            "值得一提的是": "还有一点",
            "令人瞩目的是": "挺让人关注的是",
            "据了解": "听说",
            "据悉": "据说",
            "据报道": "看到消息说",
            "相关数据表明": "数据看起来",
            "分析认为": "有人分析说",
            "专家指出": "有专家说",
        }

        for ai_phrase, natural in replace_map.items():
            if ai_phrase in text:
                replacements.append({
                    "original": ai_phrase,
                    "suggestion": natural,
                })

        return replacements


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = PatternDetector()

    # 测试：典型 AI 文
    ai_text = """值得注意的是，人工智能技术日益增长，在各行各业发挥着举足轻重的作用。
综上所述，这无疑是一次至关重要的技术变革。
与此同时，相关数据表明，AI 产业正在蓬勃发展、如火如荼。
不难发现，随着技术的不断进步，我们的生活也在发生日新月异的变化。
毋庸置疑，这标志着一个新时代的到来。"""

    result = detector.detect(ai_text)
    print("=== AI 文测试 ===")
    print(f"AI 分数: {result['ai_score']:.0f}")
    print(result["details"])
    print(f"命中模式数: {result['pattern_count']}")
    print()

    # 测试：比较自然的文
    human_text = """我今天刷到个新闻，说有人钓了条大鱼，给我看呆了都。
说实话，钓鱼这事儿吧，真的靠运气，也靠耐心。
你别说，有些人往那一坐就是一整天，我可坐不住。
不过话说回来，能钓上大鱼的感觉肯定特别爽吧？
你们平时钓鱼吗？评论区聊聊呗。"""

    result2 = detector.detect(human_text)
    print("=== 人写的测试 ===")
    print(f"AI 分数: {result2['ai_score']:.0f}")
    print(result2["details"])
    print(f"命中模式数: {result2['pattern_count']}")
