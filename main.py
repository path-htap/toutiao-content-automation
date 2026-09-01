#!/usr/bin/env python3
"""今日头条文案自动化 - 主入口

串联全部模块：抓取 → 选题 → 文案 → 配图 → 排版 → 去AI味 → 检测 → 发布

用法:
    python main.py              # 执行完整流水线
    python main.py --dry-run    # 空运行（仅测试环境）
    python main.py --phase 2    # 仅执行指定阶段
    python main.py --force      # 跳过断点续跑，从头开始
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"

# 日志配置
def setup_logging():
    """配置日志，同时输出到控制台和文件"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # 文件
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
    )
    return log_file


logger = logging.getLogger("main")


# ─── 阶段定义 ───────────────────────────────────────────

PHASES = {
    1: ("环境检查", "check_environment"),
    2: ("热点抓取", "scrape_hot_topics"),
    3: ("主题生成", "generate_topics"),
    4: ("文案撰写", "write_articles"),
    5: ("图片搜索", "search_images"),
    6: ("排版布局", "build_layout"),
    7: ("去AI味", "humanize_text"),
    8: ("AIGC检测", "check_aigc"),
    9: ("飞书发布", "publish_to_feishu"),
}


# ─── 环境检查 ───────────────────────────────────────────

def check_environment() -> bool:
    """检查必需的环境变量是否配置"""
    required_keys = [
        "ZHIPU_API_KEY",
        "PEXELS_API_KEY",
        "FEISHU_WEBHOOK",
    ]
    optional_keys = [
        "UNSPLASH_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "SILICONFLOW_API_KEY",
        "ZHUQUE_API_KEY",
    ]

    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        logger.error(f"缺少必需环境变量: {', '.join(missing)}")
        logger.info("请参考 .env.example 配置环境变量或 GitHub Secrets")
        return False

    optional_missing = [k for k in optional_keys if not os.getenv(k)]
    if optional_missing:
        logger.warning(f"可选环境变量未配置: {', '.join(optional_missing)}")

    logger.info("环境检查通过")
    return True


# ─── 各阶段执行函数 ─────────────────────────────────────

def scrape_hot_topics() -> dict:
    """Phase 2: 抓取热点数据"""
    from scrapers.toutiao import ToutiaoScraper
    from scrapers.multi_platform import MultiPlatformScraper

    logger.info("开始抓取热点数据...")
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).strftime("%Y%m%d")

    # 今日头条热榜
    toutiao = ToutiaoScraper()
    toutiao_data = toutiao.fetch()

    # 多平台聚合
    multi = MultiPlatformScraper()
    multi_data = multi.fetch()

    result = {
        "date": today,
        "toutiao": toutiao_data,
        "multi_platform": multi_data,
        "fetched_at": datetime.now(tz).isoformat(),
    }

    output_file = OUTPUT_DIR / f"hot_topics_{today}.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"热点抓取完成: 今日头条 {len(toutiao_data)} 条, 多平台 {len(multi_data)} 条")
    logger.info(f"数据保存到: {output_file}")
    return result


def generate_topics(hot_topics: dict = None) -> dict:
    """Phase 3: 生成选题"""
    from processors.topic_analyzer import TopicAnalyzer
    from processors.dedup import DedupChecker

    logger.info("开始生成选题...")
    if hot_topics is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        data_file = OUTPUT_DIR / f"hot_topics_{today}.json"
        if not data_file.exists():
            logger.error("未找到热点数据文件，请先执行 Phase 2")
            return {}
        with open(data_file, "r", encoding="utf-8") as f:
            hot_topics = json.load(f)

    analyzer = TopicAnalyzer()
    topics = analyzer.analyze(hot_topics)

    dedup = DedupChecker()
    topics = dedup.filter(topics)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"topics_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

    logger.info(f"选题生成完成: {len(topics)} 个有效选题")
    return topics


def write_articles(topics: dict = None) -> list:
    """Phase 4: 撰写文案"""
    from writers.article_agent import ArticleAgent

    logger.info("开始撰写文案...")
    if topics is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        topics_file = OUTPUT_DIR / f"topics_{today}.json"
        if not topics_file.exists():
            logger.error("未找到选题文件，请先执行 Phase 3")
            return []
        with open(topics_file, "r", encoding="utf-8") as f:
            topics = json.load(f)

    agent = ArticleAgent()
    articles = agent.generate_articles(topics)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"articles_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    logger.info(f"文案撰写完成: {len(articles)} 篇")
    return articles


def search_images(articles: list = None) -> list:
    """Phase 5: 搜索配图"""
    from images.search_api import ImageSearcher
    from images.matcher import ImageMatcher

    logger.info("开始搜索配图...")
    if articles is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        articles_file = OUTPUT_DIR / f"articles_{today}.json"
        if not articles_file.exists():
            logger.error("未找到文案文件，请先执行 Phase 4")
            return []
        with open(articles_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

    searcher = ImageSearcher()
    matcher = ImageMatcher(searcher)
    articles_with_images = matcher.match_images(articles)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"articles_with_images_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(articles_with_images, f, ensure_ascii=False, indent=2)

    logger.info(f"配图搜索完成: {len(articles_with_images)} 篇")
    return articles_with_images


def build_layout(articles: list = None) -> list:
    """Phase 6: 排版布局"""
    from layout.html_builder import HTMLBuilder

    logger.info("开始排版布局...")
    if articles is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        articles_file = OUTPUT_DIR / f"articles_with_images_{today}.json"
        if not articles_file.exists():
            logger.error("未找到配图文案文件，请先执行 Phase 5")
            return []
        with open(articles_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

    builder = HTMLBuilder()
    html_files = builder.build_all(articles)

    logger.info(f"排版完成: {len(html_files)} 个 HTML 文件")
    return html_files


def humanize_text(articles: list = None) -> list:
    """Phase 7: 去AI味"""
    from humanizer.rewrite import Humanizer

    logger.info("开始去AI味处理...")
    if articles is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        articles_file = OUTPUT_DIR / f"articles_with_images_{today}.json"
        if not articles_file.exists():
            logger.error("未找到文案文件，请先执行 Phase 5")
            return []
        with open(articles_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

    humanizer = Humanizer()
    humanized = humanizer.process(articles)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"articles_humanized_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(humanized, f, ensure_ascii=False, indent=2)

    logger.info(f"去AI味完成: {len(humanized)} 篇")
    return humanized


def check_aigc(articles: list = None) -> dict:
    """Phase 8: AIGC检测"""
    from checker.zhuque import ZhuqueChecker

    logger.info("开始AIGC检测...")
    if articles is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        articles_file = OUTPUT_DIR / f"articles_humanized_{today}.json"
        if not articles_file.exists():
            logger.error("未找到去AI味文案文件，请先执行 Phase 7")
            return {}
        with open(articles_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

    checker = ZhuqueChecker()
    report = checker.check_articles(articles)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"aigc_report_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"AIGC检测完成: {report.get('passed', 0)}/{report.get('total', 0)} 篇通过")
    return report


def publish_to_feishu(articles: list = None, report: dict = None) -> bool:
    """Phase 9: 飞书发布"""
    from feishu.notify import FeishuNotifier
    from feishu.approval import ApprovalGate

    logger.info("开始飞书发布...")
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).strftime("%Y%m%d")

    if articles is None:
        articles_file = OUTPUT_DIR / f"articles_humanized_{today}.json"
        if articles_file.exists():
            with open(articles_file, "r", encoding="utf-8") as f:
                articles = json.load(f)

    if report is None:
        report_file = OUTPUT_DIR / f"aigc_report_{today}.json"
        if report_file.exists():
            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)

    # 推送成品到飞书审阅
    notifier = FeishuNotifier()
    notifier.send_summary(articles, report)

    # 审批门（在 GitHub Actions 中，这一步仅推送通知，
    # 实际审批需用户在飞书回复，下次运行时检查审批状态）
    gate = ApprovalGate()
    gate.submit_for_review(articles, report)

    logger.info("飞书发布完成（等待用户审批）")
    return True


# ─── 流水线执行 ─────────────────────────────────────────

def run_pipeline(start_phase: int = 1, force: bool = False):
    """执行完整流水线"""
    tz = timezone(timedelta(hours=8))
    start_time = datetime.now(tz)
    logger.info(f"流水线启动 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 断点续跑：检查上次运行状态
    state_file = OUTPUT_DIR / "pipeline_state.json"
    if not force and state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        if state.get("completed") is False:
            start_phase = state.get("current_phase", 1)
            logger.info(f"检测到未完成的运行，从 Phase {start_phase} 续跑")

    results = {}
    for phase_num in range(start_phase, 10):
        phase_name, func_name = PHASES[phase_num]
        logger.info(f"{'='*50}")
        logger.info(f"Phase {phase_num}: {phase_name}")
        logger.info(f"{'='*50}")

        try:
            func = globals()[func_name]
            # 传递上一阶段结果
            if phase_num == 1:
                result = func()
            elif phase_num == 2:
                result = func()
            elif phase_num == 3:
                result = func(results.get(2))
            elif phase_num == 4:
                result = func(results.get(3))
            elif phase_num == 5:
                result = func(results.get(4))
            elif phase_num == 6:
                result = func(results.get(5))
            elif phase_num == 7:
                result = func(results.get(5))  # 去AI味基于配图前的文案
            elif phase_num == 8:
                result = func(results.get(7))
            elif phase_num == 9:
                result = func(results.get(7), results.get(8))

            results[phase_num] = result

            # 更新状态
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "current_phase": phase_num + 1,
                    "completed": phase_num == 9,
                    "last_run": datetime.now(tz).isoformat()
                }, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Phase {phase_num} 失败: {e}", exc_info=True)
            logger.info(f"可使用 --phase {phase_num} 重新执行此阶段")
            # 发送飞书错误通知
            try:
                from feishu.notify import FeishuNotifier
                notifier = FeishuNotifier()
                notifier.send_error(f"Phase {phase_num}: {PHASES[phase_num][0]}", str(e))
            except Exception as notify_err:
                logger.warning(f"发送飞书错误通知失败: {notify_err}")
            return False

    end_time = datetime.now(tz)
    duration = (end_time - start_time).total_seconds()
    logger.info(f"流水线完成 - 耗时 {duration:.1f} 秒")
    return True


# ─── 入口 ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="今日头条文案自动化")
    parser.add_argument("--dry-run", action="store_true", help="空运行（仅检查环境）")
    parser.add_argument("--phase", type=int, choices=range(1, 10), help="仅执行指定阶段")
    parser.add_argument("--force", action="store_true", help="从头开始，忽略断点续跑")
    args = parser.parse_args()

    setup_logging()

    if args.dry_run:
        logger.info("空运行模式 - 仅检查环境")
        ok = check_environment()
        sys.exit(0 if ok else 1)

    # Phase 1: 环境检查
    if not check_environment():
        sys.exit(1)

    if args.phase:
        # 单阶段执行
        phase_name, func_name = PHASES[args.phase]
        logger.info(f"执行 Phase {args.phase}: {phase_name}")
        func = globals()[func_name]
        func()
    else:
        # 完整流水线
        run_pipeline(force=args.force)


if __name__ == "__main__":
    main()
