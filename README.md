# 今日头条文案自动化

> 通过 GitHub Actions 云端定时运行，零服务器成本、零 LLM API 费用，手机飞书审阅发布。

## 快速开始

### 1. 注册免费 API

| API | 注册地址 | 免费额度 |
|-----|---------|---------|
| 智谱AI | https://open.bigmodel.cn/usercenter/apikeys | GLM-4-Flash 永久免费 |
| Pexels | https://www.pexels.com/api/ | 200次/h |
| Unsplash | https://unsplash.com/developers | 50次/h |
| 朱雀AI检测 | https://matrix.tencent.com | 20次/天 |
| 飞书机器人 | https://open.feishu.cn/app | 免费 |

### 2. 部署到 GitHub

```bash
# 克隆仓库
git clone <your-repo-url>
cd toutiao-content-automation

# 安装依赖
pip install -r requirements.txt

# 复制配置模板
cp .env.example .env
# 编辑 .env 填入 API Key

# 空运行测试
python main.py --dry-run

# 完整运行
python main.py
```

### 3. 配置 GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：
- `ZHIPU_API_KEY` - 智谱AI API Key
- `PEXELS_API_KEY` - Pexels API Key
- `UNSPLASH_API_KEY` - Unsplash API Key
- `ZHUQUE_API_KEY` - 朱雀检测 API Key
- `FEISHU_WEBHOOK` - 飞书 Webhook URL
- `FEISHU_APP_ID` - 飞书应用 App ID
- `FEISHU_APP_SECRET` - 飞书应用 App Secret

### 4. 启用自动运行

代码推送到 GitHub 后，工作流会在每天北京时间 08:00 自动运行。
也可在 Actions 页面手动触发 (workflow_dispatch)。

## 项目结构

```
├── .github/workflows/daily.yml  # GitHub Actions 定时触发
├── scrapers/                    # 热点抓取模块
├── processors/                  # 数据处理模块
├── writers/                     # 文案生成模块
├── images/                      # 图片搜索模块
├── layout/                      # 排版布局模块
├── humanizer/                   # 去AI味模块
├── checker/                     # AIGC检测模块
├── feishu/                      # 飞书通知模块
├── config/                      # 配置文件
├── output/                      # 成品输出
├── logs/                        # 运行日志
├── main.py                      # 主入口
└── requirements.txt             # Python 依赖
```

## 命令用法

```bash
python main.py              # 完整流水线
python main.py --dry-run    # 仅检查环境
python main.py --phase 2    # 仅执行 Phase 2（热点抓取）
python main.py --force      # 从头开始，忽略断点续跑
```

## 流水线阶段

| Phase | 名称 | 说明 |
|-------|------|------|
| 1 | 环境检查 | 检查 API Key 等配置 |
| 2 | 热点抓取 | 今日头条 + 多平台热榜 |
| 3 | 主题生成 | LLM 分析热点，生成选题 |
| 4 | 文案撰写 | LLM 生成多篇不同风格文案 |
| 5 | 图片搜索 | Pexels/Unsplash 自动配图 |
| 6 | 排版布局 | Jinja2 生成 HTML 成品 |
| 7 | 去AI味 | 规则+LLM 去除 AI 写作痕迹 |
| 8 | AIGC检测 | 朱雀AI检测验证 |
| 9 | 飞书发布 | 推送飞书审阅→发布 |

## 技术栈

- **运行环境**: GitHub Actions（免费）
- **LLM**: 智谱AI GLM-4-Flash（完全免费）
- **图片**: Pexels + Unsplash API（免费商用）
- **前端**: 飞书（替代 Web 前端）
- **语言**: Python 3.11+
