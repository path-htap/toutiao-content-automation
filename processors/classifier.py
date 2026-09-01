"""话题分类器

按主题自动分类，生成话题标签。
"""

import json
import logging

logger = logging.getLogger(__name__)

# 分类规则
CATEGORY_RULES = {
    "科技": ["AI", "人工智能", "芯片", "手机", "互联网", "软件", "程序", "数据", "云", "5G"],
    "财经": ["股票", "基金", "经济", "金融", "投资", "楼市", "汇率", "GDP", "通胀"],
    "社会": ["民生", "教育", "医疗", "就业", "社保", "交通", "安全", "法律"],
    "娱乐": ["明星", "影视", "音乐", "综艺", "游戏", "直播"],
    "体育": ["足球", "篮球", "奥运", "赛事", "运动员", "联赛"],
    "国际": ["美国", "日本", "欧洲", "俄罗斯", "国际", "外交", "全球"],
}


class Classifier:
    """话题分类器"""

    def classify(self, topics: list) -> list:
        """对选题列表进行分类

        Args:
            topics: 选题列表

        Returns:
            添加了 category 和 tags 字段的选题列表
        """
        for topic in topics:
            title = topic.get("title", "") + " " + topic.get("summary", "")
            keywords = topic.get("keywords", [])

            # 合并文本用于分类
            text = title + " " + " ".join(keywords)

            category, tags = self._match_category(text)
            topic["category"] = category
            topic["tags"] = tags

        return topics

    def _match_category(self, text: str) -> tuple:
        """匹配分类

        Returns:
            (category, tags) 元组
        """
        matched_categories = []
        matched_tags = []

        for category, keywords in CATEGORY_RULES.items():
            hits = [kw for kw in keywords if kw in text]
            if hits:
                matched_categories.append((category, len(hits)))
                matched_tags.extend(hits)

        if matched_categories:
            # 取命中次数最多的分类
            matched_categories.sort(key=lambda x: x[1], reverse=True)
            return matched_categories[0][0], list(set(matched_tags))

        return "综合", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    clf = Classifier()
    test = [{"title": "AI芯片最新突破", "summary": "人工智能芯片", "keywords": ["AI", "芯片"]}]
    result = clf.classify(test)
    print(json.dumps(result, ensure_ascii=False, indent=2))
