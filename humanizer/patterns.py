"""AI 写作模式检测

识别 30+ 种 AI 写作高频模式和套路化表达。
参考: Humanizer-zh 项目规则
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# AI 高频词和套路化表达（30+ 模式）
AI_PATTERNS = [
    # 过渡词/连接词滥用
    "值得注意的是", "综上所述", "总的来说", "总而言之", "由此可见",
    "不难发现", "不难看出", "显而易见", "毋庸置疑", "不可否认",
    "首先.*其次.*最后", "一方面.*另一方面", "与此同时", "在此基础上",
    # 空洞表达
    "至关重要", "举足轻重", "不容忽视", "日益增长", "蓬勃发展",
    "日新月异", "突飞猛进", "方兴未艾", "如火如荼",
    # AI 特征句式
    "作为.*的重要组成部分", "在.*的背景下", "随着.*的发展",
    ".*扮演着.*角色", ".*发挥着.*作用", ".*提供了.*参考",
    ".*具有重要的.*意义", "为.*提供了.*借鉴",
    # 评价/总结句式
    "可以说", "不得不提", "令人瞩目的是", "值得关注的是",
    "这无疑", "这充分", "这标志着",
]

# AI 高频词统计（用于计算 AI 味程度）
AI_FREQUENCY_WORDS = [
    "值得", "综合", "重要", "关键", "核心", "显著",
    "有效", "高效", "优化", "提升", "促进", "推动",
    "实现", "构建", "打造", "赋能", "助力", "聚焦",
]


class PatternDetector:
    """AI 写作模式检测器"""

    def __init__(self):
        self.patterns = [re.compile(p) for p in AI_PATTERNS]
        self.freq_words = AI_FREQUENCY_WORDS

    def detect(self, text: str) -> dict:
        """检测文本中的 AI 写作模式

        Args:
            text: 待检测文本

        Returns:
            检测结果: {patterns_found, freq_count, ai_score, details}
        """
        # 1. 模式匹配
        matches = []
        for i, pattern in enumerate(self.patterns):
            found = pattern.findall(text)
            if found:
                pattern_str = AI_PATTERNS[i]
                matches.append({
                    "pattern": pattern_str,
                    "count": len(found),
                })

        # 2. 高频词统计
        freq_hits = {}
        for word in self.freq_words:
            count = text.count(word)
            if count > 0:
                freq_hits[word] = count

        # 3. 计算 AI 味分数 (0-100, 越高越像 AI)
        pattern_score = min(len(matches) * 10, 50)
        freq_score = min(sum(freq_hits.values()) * 2, 50)
        ai_score = pattern_score + freq_score

        return {
            "patterns_found": matches,
            "freq_words": freq_hits,
            "pattern_count": len(matches),
            "freq_word_count": sum(freq_hits.values()),
            "ai_score": ai_score,
            "details": f"发现 {len(matches)} 个 AI 模式, {sum(freq_hits.values())} 个高频词",
        }

    def get_replacements(self, text: str) -> list:
        """获取需要替换的 AI 模式和建议替换词

        Returns:
            [{original, suggestion, context}]
        """
        replacements = []

        # AI 模式 → 自然表达替换表
        replace_map = {
            "值得注意的是": "有意思的是",
            "综上所述": "说到底",
            "总的来说": "整体来看",
            "不难发现": "能看到",
            "显而易见": "很明显",
            "至关重要": "最关键的",
            "举足轻重": "很重要",
            "日益增长": "越来越多",
            "蓬勃发展": "发展很快",
            "突飞猛进": "进步很快",
            "与此同时": "同时",
            "可以说": "",
            "这无疑": "这",
            "值得关注的是": "有意思的是",
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
    test_text = "值得注意的是，AI技术日益增长，发挥着重要作用。综上所述，这无疑是关键。"
    result = detector.detect(test_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n替换建议:")
    print(json.dumps(detector.get_replacements(test_text), ensure_ascii=False, indent=2))
