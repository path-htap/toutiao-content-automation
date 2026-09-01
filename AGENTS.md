# AGENTS.md - 今日头条文案自动化运行

> 本文件供 AI Agent（Codex / Claude Code / TRAE / 任意支持 AGENTS.md 的工具）使用，定义项目全貌、架构、分阶段实施计划、资源清单与验收标准。
>
> 制定日期：2026-09-01 ｜ 时区：Asia/Shanghai ｜ 版本：v2.0（GitHub Actions 架构）

---

## 目录

1. [项目概述](#1-项目概述)
2. [架构设计](#2-架构设计)
3. [免费 LLM API 选型](#3-免费-llm-api-选型)
4. [GitHub Actions 配置](#4-github-actions-配置)
5. [飞书集成方案](#5-飞书集成方案)
6. [实施计划（9个阶段）](#6-实施计划9个阶段)
7. [资源清单](#7-资源清单)
8. [编码规范](#8-编码规范)
9. [重要注意事项](#9-重要注意事项)

---

## 1. 项目概述

构建一套端到端的今日头条内容自动化生产系统，通过 GitHub Actions 云端定时运行，零服务器成本、零 LLM API 费用，用户仅需手机飞书审阅和发布。

**核心目标：**

- GitHub Actions 定时触发，云端自动运行，不需要开电脑
- 免费 LLM API 生成文案，零 API 费用
- 飞书作为唯一用户界面，替代 Web 前端
- 全流程：抓取 → 选题 → 写作 → 配图 → 排版 → 去AI味 → 检测 → 飞书发布

**技术栈：** Python + GitHub Actions + 智谱AI GLM-4-Flash + 飞书 OpenAPI

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                   GitHub Actions                     │
│              (cron 定时触发，云端运行)                 │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 热点抓取  │→│ 主题生成  │→│ 文案撰写  │          │
│  │ (Python) │  │ (LLM API)│  │ (LLM API)│          │
│  └──────────┘  └──────────┘  └──────────┘          │
│       ↓                              ↓               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 图片搜索  │→│ 排版布局  │→│ 去AI味    │          │
│  │ (Pexels  │  │ (Jinja2) │  │ (规则+LLM)│          │
│  │  API)    │  └──────────┘  └──────────┘          │
│  └──────────┘        ↓                ↓             │
│                ┌──────────┐  ┌──────────┐          │
│                │ AIGC检测 │←│ 飞书推送  │          │
│                │ (朱雀API)│  │ (Webhook)│          │
│                └──────────┘  └──────────┘          │
└─────────────────────────┬───────────────────────────┘
                           ↓
                    ┌──────────────┐
                    │  用户手机飞书  │
                    │  审阅 → 发布   │
                    └──────────────┘
```

### 2.2 数据流

```
WebSearch/RSS → JSON热点数据 → LLM生成选题JSON → LLM生成文案JSON
→ 图片URL列表 → HTML成品 → 去AI味后文案 → AIGC检测报告
→ 飞书文档 + 飞书消息通知
```

### 2.3 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 运行环境 | GitHub Actions | 免费、云端、定时、无需开电脑 |
| LLM API | 智谱AI GLM-4-Flash | 完全免费、中文优秀、OpenAI兼容 |
| LLM 备选 | 硅基流动 / 百度千帆 | 永久免费模型、国内低延迟 |
| 前端界面 | 飞书（替代Web前端） | 用户手机即可操作、无需开发 |
| 代码开发 | TRAE 辅助编写 → /workspace | 我写代码，用户推到GitHub |
| 隧道依赖 | 无 | 不依赖任何临时隧道 |
| ShunCode MCP | 仅开发阶段参考（可选） | 运行环境为GitHub Actions |

---

## 3. 免费 LLM API 选型

### 3.1 主力 API：智谱AI GLM-4-Flash

| 项目 | 详情 |
|------|------|
| 模型 | GLM-4-Flash（完全免费，永久免费） |
| 上下文 | 128K |
| 并发 | 30 QPS |
| 注册地址 | https://open.bigmodel.cn/usercenter/apikeys |
| Base URL | `https://open.bigmodel.cn/api/paas/v4/` |
| 信用卡 | 不需要 |
| 新用户额度 | 2000万 Token（永久有效） |
| 接口格式 | OpenAI 兼容 |
| 中文能力 | 国内第一梯队 |

**调用示例：**

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("ZHIPU_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)

response = client.chat.completions.create(
    model="glm-4-flash",
    messages=[{"role": "user", "content": "你好"}]
)
```

### 3.2 备选 API（多平台冗余，自动切换）

| 平台 | 免费模型 | 额度 | Base URL | 特点 |
|------|---------|------|----------|------|
| 硅基流动 | Qwen2.5-7B | 9B以下永久免费 | `https://api.siliconflow.cn/v1` | 国内低延迟 |
| 百度千帆 | ERNIE-Speed-8K | 永久免费不限量 | `https://qianfan.baidubce.com/v2` | 50 QPS |
| Google Gemini | Gemini 3.5 Flash | 15 RPM, 1500 RPD | `https://generativelanguage.googleapis.com/v1beta` | 多模态、需VPN |
| Groq | Llama 3.3 70B | 30 RPM, 14400 RPD | `https://api.groq.com/openai/v1` | 超低延迟、英文强 |
| GitHub Models | 16个免费模型 | 免费额度 | `https://models.github.ai/inference` | 无需额外注册 |

### 3.3 LLM 用量估算

| 环节 | 每次调用 | 每日次数 | 日用量 |
|------|---------|---------|--------|
| 选题生成 | ~2K tokens | 5次 | ~10K |
| 文案撰写 | ~4K tokens | 15次（5选题×3篇） | ~60K |
| 去AI味重写 | ~4K tokens | 10次 | ~40K |
| **日总用量** | | | **~110K tokens** |

智谱AI 2000万 Token 够用约 **180 天**，用完后 GLM-4-Flash 仍永久免费，所以实际上**无限使用**。

> 数据来源：2026年免费大模型API汇总 [$TRAE_REF](https://blog.csdn.net/k0933/article/details/161116701) ｜ awesome-free-llm-apis [$TRAE_REF](https://github.com/open-free-llm-api/awesome-freellm-apis/blob/main/README.zh-CN.md)

---

## 4. GitHub Actions 配置

### 4.1 免费额度

| 项目 | 免费额度 |
|------|---------|
| 公开仓库 | **无限分钟** |
| 私有仓库 | 2000 分钟/月 |
| 并发任务 | 20 个 |
| 单任务最大运行 | 6 小时 |
| 操作系统 | Linux（1x 倍率） |

每日运行 1 次，每次约 15-30 分钟，月用量约 450-900 分钟。**公开仓库完全免费，私有仓库也够用。**

### 4.2 工作流文件模板

```yaml
# .github/workflows/daily.yml
name: 今日头条文案自动化
on:
  schedule:
    - cron: '0 0 * * *'  # UTC 00:00 = 北京时间 08:00
  workflow_dispatch:      # 支持手动触发

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: 设置 Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: 安装依赖
        run: pip install -r requirements.txt
      - name: 执行流水线
        env:
          ZHIPU_API_KEY: ${{ secrets.ZHIPU_API_KEY }}
          PEXELS_API_KEY: ${{ secrets.PEXELS_API_KEY }}
          UNSPLASH_API_KEY: ${{ secrets.UNSPLASH_API_KEY }}
          FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}
          FEISHU_APP_ID: ${{ secrets.FEISHU_APP_ID }}
          FEISHU_APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
        run: python main.py
      - name: 上传成品
        uses: actions/upload-artifact@v4
        with:
          name: daily-output
          path: output/
          retention-days: 7
```

### 4.3 GitHub Secrets 配置

在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret 名 | 说明 |
|-----------|------|
| `ZHIPU_API_KEY` | 智谱AI API Key |
| `PEXELS_API_KEY` | Pexels API Key |
| `UNSPLASH_API_KEY` | Unsplash API Key |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |
| `FEISHU_APP_ID` | 飞书应用 App ID（用于创建文档） |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |

---

## 5. 飞书集成方案

飞书替代 Web 前端，承担以下功能：

| 功能 | 飞书能力 | 实现方式 |
|------|---------|---------|
| 热点推送 | 消息卡片 | Webhook 发送交互卡片 |
| 选题审阅 | 消息+按钮 | 卡片内嵌"采用/不采用"按钮 |
| 文案预览 | 飞书文档 | OpenAPI 创建 Docx |
| 图片展示 | 飞书云盘 | OpenAPI 上传图片+内嵌文档 |
| 排版预览 | 飞书文档 | 富文本格式展示 |
| 审批发布 | 消息回复 | 用户回复"发布"触发发布 |
| 运行通知 | 消息推送 | Webhook 推送运行状态 |
| 历史记录 | 飞书多维表格 | OpenAPI 创建 Base 记录 |

### 5.1 飞书机器人创建步骤

1. 访问 https://open.feishu.cn/app 创建企业自建应用
2. 获取 App ID 和 App Secret
3. 配置机器人能力，获取 Webhook URL
4. 权限申请：消息发送、文档创建、云盘上传、多维表格读写
5. 将 App ID / App Secret / Webhook URL 存入 GitHub Secrets

---

## 6. 实施计划（9个阶段）

> **图例说明：**
> - 🟠 **[用户]** = 需要你亲自操作的任务
> - 🔵 **[AI]** = 我（TRAE）自动完成的任务
> - ✅ **验收** = 该阶段验收标准

---

### Phase 1: 环境搭建与项目初始化

**目标：** 创建 GitHub 仓库、注册 API、搭建项目骨架

#### 任务清单

- 🟠 **[用户]** 注册智谱AI：https://open.bigmodel.cn/usercenter/apikeys → 获取 API Key
- 🟠 **[用户]** 注册 Pexels API：https://www.pexels.com/api/ → 获取 API Key
- 🟠 **[用户]** 注册 Unsplash API：https://unsplash.com/developers → 获取 API Key
- 🟠 **[用户]** 创建飞书机器人：https://open.feishu.cn/app → 获取 App ID / Secret / Webhook
- 🟠 **[用户]** 创建 GitHub 仓库（公开或私有），将 API Key 存入 Secrets
- 🟠 **[用户]** 确认技术选型，审阅 AGENTS.md
- 🔵 **[AI]** 编写完整项目骨架代码（写到 /workspace，用户推到 GitHub）
- 🔵 **[AI]** 编写 requirements.txt 依赖清单
- 🔵 **[AI]** 编写 .env.example 配置模板
- 🔵 **[AI]** 编写 .github/workflows/daily.yml 工作流文件
- 🔵 **[AI]** 编写 README.md 项目说明

#### 验收标准

- ✅ GitHub 仓库创建成功，代码推送成功
- ✅ GitHub Secrets 全部配置（6个）
- ✅ requirements.txt 安装无报错
- ✅ main.py 可执行空运行（`python main.py --dry-run`）
- ✅ GitHub Actions 工作流文件语法正确
- ✅ 手动触发 workflow_dispatch 成功运行

---

### Phase 2: 热点数据抓取模块

**目标：** 抓取今日头条及多平台热点数据

#### 任务清单

- 🟠 **[用户]** 确认热点数据源范围（除今日头条外是否需百度热搜、微博、知乎等）
- 🟠 **[用户]** 提供关注关键词和过滤关键词
- 🔵 **[AI]** 编写 `scrapers/toutiao.py`：今日头条热榜抓取
- 🔵 **[AI]** 编写 `scrapers/multi_platform.py`：多平台热搜聚合（TrendRadar/newsnow 参考逻辑）
- 🔵 **[AI]** 实现数据结构化存储：JSON（排名/标题/热度值/来源/时间戳/URL）
- 🔵 **[AI]** 实现关键词过滤和去重
- 🔵 **[AI]** 编写 `feishu/notify.py`：热点列表推送飞书消息卡片

#### 验收标准

- ✅ 今日头条热榜 TOP50 成功抓取，含 6 个字段
- ✅ 多平台聚合数据至少覆盖 5 个平台
- ✅ 关键词过滤正常（频率词匹配、过滤词排除）
- ✅ JSON 数据正确写入 output/ 目录
- ✅ 飞书消息卡片推送成功，含热点列表
- ✅ 抓取失败时记录日志不崩溃

---

### Phase 3: 热点整理与主题生成

**目标：** LLM 分析热点趋势，生成多角度选题

#### 任务清单

- 🟠 **[用户]** 在飞书审阅选题清单，回复"采用X、Y"或"不采用Z"
- 🟠 **[用户]** 指定每期文案数量（如 3-5 篇）及偏好主题
- 🔵 **[AI]** 编写 `processors/topic_analyzer.py`：调智谱AI 分析热点，每热点生成 2-3 个角度
- 🔵 **[AI]** 编写 `processors/classifier.py`：按主题自动分类
- 🔵 **[AI]** 编写 `processors/dedup.py`：与历史选题比对，相似度 >70% 标记重复
- 🔵 **[AI]** 输出选题清单 JSON（标题/摘要/关键词/受众/类型/热度评分）
- 🔵 **[AI]** 飞书推送选题审阅卡片（含采用/不采用按钮）

#### 验收标准

- ✅ 从当日热点生成不少于 5 个有效选题
- ✅ 每个选题含 2-3 个不同角度
- ✅ 选题分类准确率 ≥ 90%
- ✅ 去重功能正常（与近 7 天比对）
- ✅ 飞书选题审阅卡片推送成功

---

### Phase 4: AI 文案撰写模块

**目标：** LLM 根据选题生成多篇不同风格文案

#### 任务清单

- 🟠 **[用户]** 在飞书审阅文案，回复质量评分（1-5）和修改意见
- 🟠 **[用户]** 提供 1-2 篇满意"范文"作为风格参考（可选）
- 🔵 **[AI]** 编写 `writers/article_agent.py`：调智谱AI，选题→素材→提纲→全文
- 🔵 **[AI]** 编写多种文案风格模板（资讯速递/深度评论/盘点列表/故事叙事）
- 🔵 **[AI]** 构建 `writers/prompts/` Prompt 库（选题分析/提纲/正文/标题优化）
- 🔵 **[AI]** 自动生成标题（主+副）、摘要（≤100字）、正文（800-2000字）
- 🔵 **[AI]** 支持范文 few-shot（如有用户提供的范文）

#### 验收标准

- ✅ 每选题生成 2-3 篇不同风格完整文案
- ✅ 每篇含主标题、副标题、摘要、正文（≥3段）、结语
- ✅ 内容与选题相关度 ≥ 85%
- ✅ 单篇生成时间 ≤ 2 分钟
- ✅ 无事实性错误

---

### Phase 5: 图片搜索与生成模块

**目标：** 自动搜索配图

#### 任务清单

- 🟠 **[用户]** 确认封面图风格偏好（如有）
- 🟠 **[用户]** 在飞书审阅配图，标注不合适图片（可替换）
- 🔵 **[AI]** 编写 `images/search_api.py`：集成 Pexels/Unsplash，按关键词搜索
- 🔵 **[AI]** 实现 API 限流和缓存（Pexels ≤200次/h，Unsplash ≤50次/h）
- 🔵 **[AI]** 编写 `images/matcher.py`：LLM 分析段落语义 → 插入配图标记 → 匹配图片
- 🔵 **[AI]** 实现图片下载和后处理（裁剪、压缩 ≤500KB）
- 🔵 **[AI]** 上传图片到飞书云盘，获取内嵌 URL

#### 验收标准

- ✅ 每篇配图 3-5 张，与内容相关度 ≥ 80%
- ✅ 搜索图片全部为免费商用许可
- ✅ API 限流正常，无 429 错误
- ✅ 缓存机制有效
- ✅ 图片体积 ≤ 500KB
- ✅ 图片上传飞书云盘成功

---

### Phase 6: 排版布局模块

**目标：** 自动排版生成 HTML 成品

#### 任务清单

- 🟠 **[用户]** 在飞书预览排版效果，选择满意版式
- 🟠 **[用户]** 确认目标发布平台（今日头条/公众号/小红书）
- 🔵 **[AI]** 编写 `layout/html_builder.py`：文案+图片 → 自包含 HTML
- 🔵 **[AI]** 编写 Jinja2 模板：头条版（大图+正文流）、公众号版（图文混排）、小红书版（卡片式）
- 🔵 **[AI]** 实现自动排版规则：标题居中、段落间距、配图居中带说明、响应式
- 🔵 **[AI]** 通过飞书 OpenAPI 创建飞书文档，内嵌排版内容

#### 验收标准

- ✅ HTML 自包含单文件（CSS 内联），可直接浏览器打开
- ✅ 排版美观，层次分明，无错位
- ✅ 手机端响应式适配正常（375px 无横向滚动）
- ✅ 至少 3 种平台版式模板
- ✅ 飞书文档创建成功，内容正确

---

### Phase 7: 去AI味处理模块

**目标：** 去除 AI 写作痕迹

#### 任务清单

- 🟠 **[用户]** 阅读去AI味后文案，评估自然度（1-5分），标注仍"AI味重"段落
- 🟠 **[用户]** 提供个人写作习惯样本（可选，帮助 AI 学习个人语气）
- 🔵 **[AI]** 编写 `humanizer/patterns.py`：识别 AI 写作模式（"值得注意的是""综上所述"等 30+ 模式）
- 🔵 **[AI]** 编写 `humanizer/rewrite.py`：调 LLM 逐段重写，注入自然表达
- 🔵 **[AI]** 实现三层处理：①词汇层（替换AI高频词）②语法层（口语化/非完美句式）③思维层（个人观点/跳跃性）
- 🔵 **[AI]** 构建改写规则库 `humanizer/rules/`：同义替换词库、口语化模板

#### 验收标准

- ✅ AI 高频词减少 ≥ 80%
- ✅ 自然度评分 ≥ 4/5（5 篇平均）
- ✅ 核心信息无丢失（覆盖率 ≥ 95%）
- ✅ 专业术语未被误改
- ✅ 三层处理全部生效（有处理记录）
- ✅ 字数变化 ≤ ±15%

---

### Phase 8: AIGC 检测验证模块

**目标：** 通过 AIGC 检测

#### 任务清单

- 🟠 **[用户]** 设定检测通过阈值（建议 AI 概率 ≤ 30%）
- 🟠 **[用户]** 审阅未通过检测的文案，决定"自动重写"或"人工修改"
- 🔵 **[AI]** 编写 `checker/zhuque.py`：朱雀AI检测 API 集成（20次/天额度管理）
- 🔵 **[AI]** 编写检测-重写循环：未通过→回 Phase 7 重写→再检测→通过则入库（最多3次）
- 🔵 **[AI]** 生成质量评分报告（AI概率/自然度/信息覆盖率/改写次数）
- 🔵 **[AI]** 飞书推送质量报告卡片

#### 验收标准

- ✅ 朱雀 AI 检测 API 集成成功
- ✅ 5 篇样本中 ≥ 4 篇通过检测（AI 概率 ≤ 30%）
- ✅ 检测-重写循环正常
- ✅ 每日 20 次额度管理正常
- ✅ 质量报告四项指标完整
- ✅ 通过检测文案归档到 output/approved/

---

### Phase 9: GitHub Actions 部署与飞书发布

**目标：** 全流水线串联，GitHub Actions 定时自动运行，飞书发布

#### 任务清单

- 🟠 **[用户]** 确认自动化时间表（如每天 8:00 北京时间）
- 🟠 **[用户]** 首周每日检查飞书运行结果，确认无异常后转全自动
- 🟠 **[用户]** 授权飞书应用发布权限
- 🔵 **[AI]** 编写 `main.py` 主入口：串联全部模块，含错误处理和断点续跑
- 🔵 **[AI]** 完善 `.github/workflows/daily.yml` 工作流
- 🔵 **[AI]** 集成飞书发布：运行完成 → 创建飞书文档 → 推送消息通知
- 🔵 **[AI]** 实现运行监控与日志：GitHub Actions 日志 + 飞书运行状态推送
- 🔵 **[AI]** 实现"飞书审批门"：生成成品先发飞书审阅，用户回复"发布"才正式发布

#### 验收标准

- ✅ 全流水线端到端运行成功
- ✅ 单次运行 ≤ 30 分钟
- ✅ GitHub Actions cron 按时自动触发
- ✅ 飞书通知每次运行后成功推送
- ✅ 断点续跑有效（某环节失败可从失败点继续）
- ✅ 运行日志完整记录
- ✅ 连续 3 天自动化运行无人工干预
- ✅ "飞书审批门"功能正常（审阅 → 发布流程闭环）

---

## 7. 资源清单

### 7.1 GitHub 参考仓库（仅参考逻辑，不直接使用）

| 项目 | 地址 | 参考用途 |
|------|------|---------|
| TrendRadar | https://github.com/zittr/TrendRadar | 热点抓取逻辑参考 |
| newsnow | https://github.com/ourongxing/newsnow | 多平台热搜 API 参考 |
| content-agent | https://github.com/qiuxchao/content-agent | LangGraph 文案 Agent 参考 |
| image-match-skills | https://github.com/chenningling/image-match-skills | 语义配图逻辑参考 |
| Humanizer-zh | https://github.com/ai-zixun/humanizer-zh | 去 AI 味规则参考 |

### 7.2 Python 依赖

```bash
pip install openai requests httpx beautifulsoup4 lxml jinja2 Pillow python-dotenv
```

| 包名 | 用途 |
|------|------|
| openai | LLM API 调用（OpenAI 兼容接口调智谱AI） |
| requests | HTTP 请求（热点抓取、图片下载） |
| httpx | 异步 HTTP 请求 |
| beautifulsoup4 | HTML 解析 |
| lxml | XML/HTML 快速解析 |
| jinja2 | 排版模板引擎 |
| Pillow | 图片处理（裁剪/压缩） |
| python-dotenv | 环境变量管理 |

### 7.3 API 注册（需用户操作）

| API | 注册地址 | 免费额度 | 用途 |
|-----|---------|---------|------|
| 智谱AI | https://open.bigmodel.cn/usercenter/apikeys | GLM-4-Flash 永久免费 | LLM 文案生成 |
| Pexels | https://www.pexels.com/api/ | 200次/h, 2万/月 | 图片搜索 |
| Unsplash | https://unsplash.com/developers | 50次/h | 高清摄影图 |
| 朱雀AI检测 | https://matrix.tencent.com | 20次/天 | AIGC 检测 |
| 飞书开放平台 | https://open.feishu.cn/app | 免费 | 消息/文档/云盘 |

### 7.4 备选 LLM API（免费，注册即用）

| 平台 | Base URL | 免费额度 | 特点 |
|------|---------|---------|------|
| 硅基流动 | `https://api.siliconflow.cn/v1` | 9B以下模型永久免费 | 国内低延迟 |
| 百度千帆 | `https://qianfan.baidubce.com/v2` | ERNIE-Speed 永久免费 | 不限量 |
| Groq | `https://api.groq.com/openai/v1` | 14400次/天 | 超低延迟 |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | 1500次/天 | 多模态 |

### 7.5 无需下载（内置能力）

| 能力 | 来源 | 用途 |
|------|------|------|
| TRAE AI Agent | 当前环境 | 辅助编写代码、生成 Prompt、设计架构 |
| WebSearch / WebFetch | 内置 | 搜索参考项目、验证 API 信息 |
| GenerateImage | 内置 | 生成封面图（开发阶段辅助） |
| html-report 技能 | 内置 Skill | 生成预览 HTML |
| Lark 插件 | 已安装 | 飞书操作（开发阶段辅助验证） |

---

## 8. 编码规范

### 8.1 项目结构

```
toutiao-content-automation/
├── .github/
│   └── workflows/
│       └── daily.yml          # GitHub Actions 定时触发
├── scrapers/                  # 热点抓取模块
│   ├── toutiao.py             # 今日头条热榜
│   ├── multi_platform.py     # 多平台聚合
│   └── rss_feeds.py           # RSS 资讯源
├── processors/                # 数据处理模块
│   ├── topic_analyzer.py     # 热点分析→选题
│   ├── classifier.py          # 话题分类
│   └── dedup.py               # 内容去重
├── writers/                   # 文案生成模块
│   ├── article_agent.py      # LLM 文案生成
│   ├── styles/                # 风格模板
│   └── prompts/               # Prompt 库
├── images/                    # 图片模块
│   ├── search_api.py         # Pexels/Unsplash 搜索
│   └── matcher.py             # 语义配图
├── layout/                    # 排版模块
│   ├── html_builder.py       # HTML 生成
│   └── templates/             # Jinja2 模板
├── humanizer/                 # 去AI味模块
│   ├── patterns.py           # AI 模式检测
│   ├── rewrite.py             # LLM 重写
│   └── rules/                 # 改写规则库
├── checker/                   # AIGC检测模块
│   └── zhuque.py              # 朱雀检测
├── feishu/                    # 飞书模块
│   ├── notify.py              # 消息推送
│   ├── doc_creator.py         # 文档创建
│   └── approval.py            # 审批流程
├── config/                    # 配置
│   ├── .env.example           # API Key 模板
│   └── sources.json           # 数据源配置
├── output/                    # 成品输出
├── logs/                      # 运行日志
├── requirements.txt           # Python 依赖
├── main.py                    # 主入口
└── README.md                  # 项目说明
```

### 8.2 编码约定

- **语言：** Python 3.11+
- **代码风格：** PEP 8，使用 type hints
- **LLM 调用：** 统一使用 OpenAI SDK（兼容智谱AI/硅基流动/Groq 等）
- **配置管理：** 所有 API Key 通过环境变量（GitHub Secrets），不硬编码
- **错误处理：** 每个模块 try/except 包裹，失败时记录日志不中断流程
- **日志格式：** `[时间][模块名][级别] 消息`
- **数据传递：** 模块间通过 JSON 文件，统一存放在 output/
- **测试：** 每个模块含 `if __name__ == "__main__":` 独立测试入口
- **文档：** 每个模块顶部 docstring 说明用途、输入输出、依赖

### 8.3 LLM 调用规范

```python
import os
from openai import OpenAI

class LLMClient:
    """统一 LLM 客户端，支持多平台切换"""

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
        }
    }

    def __init__(self, provider="zhipu"):
        config = self.PROVIDERS[provider]
        self.client = OpenAI(
            api_key=os.getenv(config["key_env"]),
            base_url=config["base_url"]
        )
        self.model = config["model"]

    def chat(self, messages, **kwargs):
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
```

---

## 9. 重要注意事项

### 9.1 法律合规

- **平台 ToS：** 抓取今日头条等平台数据需遵守服务条款，优先使用公开 API 或 RSS 源
- **图片版权：** Pexels/Unsplash 图片均为免费商用许可
- **AIGC 标识：** 部分平台要求标注 AI 生成内容，需了解目标平台政策
- **数据安全：** API Key 通过 GitHub Secrets 存储，不硬编码，不入 Git

### 9.2 技术注意

- **LLM 速率限制：** 智谱AI 30 QPS，足够使用；但需加重试机制
- **GitHub Actions 时区：** cron 用 UTC 时间，北京时间 = UTC + 8（`0 0 * * *` = 北京 08:00）
- **GitHub Actions 超时：** 单任务最大 6 小时，设置 `timeout-minutes: 30`
- **去AI味平衡：** 过度改写降低质量，需平衡"通过检测"和"可读性"
- **飞书审批门：** 生成成品先发飞书审阅，用户确认后才发布，防止翻车
- **多平台冗余：** 主力 LLM 故障时自动切换备选 API

### 9.3 运营注意

- **人工审核环节：** "去AI味→检测"和"排版→发布"之间设飞书审批门
- **内容去重：** 维护去重库，避免与历史内容重复
- **热点时效性：** 从抓取到发布全链路应在 2 小时内
- **成本控制：** 全部使用免费额度，零成本运行
- **监控告警：** 运行失败时飞书推送告警消息

### 9.4 开发流程

1. **我（TRAE）编写代码** → 写到 `/workspace` 目录
2. **用户审阅代码** → 确认无误后推到 GitHub 仓库
3. **配置 Secrets** → 在 GitHub 仓库 Settings 中添加 API Key
4. **手动触发测试** → workflow_dispatch 验证流程
5. **配置定时** → cron schedule 自动触发
6. **飞书审阅** → 每天在手机飞书上审阅和发布

---

## 附录：LLM 多平台切换策略

```python
# 自动故障切换逻辑
PROVIDER_PRIORITY = ["zhipu", "siliconflow", "baidu"]

def get_llm_response(messages):
    for provider in PROVIDER_PRIORITY:
        try:
            client = LLMClient(provider)
            return client.chat(messages)
        except Exception as e:
            log.warning(f"{provider} 调用失败: {e}，切换下一个")
            continue
    raise Exception("所有 LLM 提供商均不可用")
```

## 附录：飞书审批门流程

```
GitHub Actions 生成成品 → 飞书推送"待审阅"消息卡片
→ 用户在手机上打开飞书文档审阅
→ 用户回复"发布" → 触发发布流程（飞书 OpenAPI 发布到目标平台）
→ 用户回复修改意见 → 触发重新生成
→ 超时 24 小时未回复 → 自动归档为"未发布"
```

## 附录：AIGC 检测工具对比

| 检测平台 | 中文准确率 | 免费额度 | 特点 |
|----------|-----------|---------|------|
| 朱雀 AI（腾讯） | 96.8% | 20次/天 | 长文检测好，覆盖新闻/公文 |
| 知网 AIGC | 99.1% | 机构授权 | 准确率最高，学术场景 |
| GPTZero | 89.5% | 有限免费 | 英文强，中文一般 |

> 数据来源：2025-2026 AI 检测市场报告
