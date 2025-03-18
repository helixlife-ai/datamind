# DataMind

## ⚗️ 您的AI驱动数据炼金炉，将任意文档点化为智慧金矿

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org)
[![Node.js](https://img.shields.io/badge/Node.js-20.x-green.svg)](https://nodejs.org/)
[![Version](https://img.shields.io/badge/version-0.3.0-green.svg)](https://github.com/helixlife-ai/datamind/releases)

[English](../README.md) | [中文](README_zh.md)

## 📖 简介

欢迎踏入数据炼金术的奇妙世界！DataMind 是一座AI驱动的知识炼丹炉，为您发掘数据背后的隐藏洞见。

**Data in, Surprise out!**

DataMind 帮你将任意文档转化为闪耀智慧的结晶：
- 投入原始文档，获得精炼知识精华
- 放入信息碎片，收获连贯完整的智慧
- 添加杂乱数据，得到清晰直观的洞见
- 注入复杂问题，提取简洁优雅的解答

无论您面对什么挑战：
- 需要深入市场洞察？投入行业报告与新闻文章 — 收获全面的市场全景分析
- 构建复杂技术文档？添加代码库与API文档 — 获得结构完美的技术手册
- 解析竞争对手动向？输入竞品数据与社交信息 — 得到精确的竞争态势图
- 规划下一个项目？放入历史文件与需求清单 — 展现条理分明的项目蓝图

就像魔法石点石成金，DataMind将为您完成从普通数据到闪耀智慧的奇妙转变：
- 运用前沿AI技术洞察文档深层含义
- 精准理解您的每一个自然语言需求
- 自动生成专业、连贯的分析报告
- 以您偏好的形式呈现最终炼制品
- 确保每一份输出既合乎逻辑又事实精准

投入您的数据，说出您的需求，让DataMind的AI魔法为您炼制完美答案！

## ✨ 核心特性

### 🎨 新增特性 (v0.3.0)
- 正式发布的第一版

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/helixlife-ai/datamind.git
cd datamind

# 安装Python依赖
pip install -r requirements.txt
playwright install chromium

# 生成测试数据
python scripts/generate_test_data.py

# 安装Node.js (如果尚未安装)
# 对于Ubuntu/Debian:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 对于MacOS (使用Homebrew):
brew install node@20

# 对于Windows:
# 请从 https://nodejs.org/en/download/ 下载并安装Node.js 20.x版本

# 安装pnpm (如果尚未安装)
npm install -g pnpm
```

### 使用示例

运行示例脚本是最简单的开始方式：

```bash
# Run the app
cd app
pnpm install
node server.js
```
浏览器打开：http://localhost:3000
将要处理的本地文档放在work_dir目录下，点击开始运行按钮。

## ⚙️ 配置

### 环境变量

项目使用环境变量进行配置。你可以通过以下两种方式设置：

1. 使用 `.env` 文件（推荐）：
   ```bash
   cp .env.example .env
   # 然后编辑 .env 文件填入你的值
   ```

2. 直接在环境中设置你的大模型（推荐claude3.7，备选DEEPSEEK）：
   ```bash
   DEFAULT_API_KEY=["your-api-key-here"]
   DEFAULT_BASE_URL=https://api.anthropic.com/v1
   DEFAULT_GENERATOR_MODEL="claude-3-7-sonnet-20250219"
   DEFAULT_REASONING_MODEL="claude-3-7-sonnet-20250219"
   ```

## 🤝 参与贡献

欢迎提交 PR 或 Issue！详细信息请参考 [贡献指南](CONTRIBUTING.md)。

## 📄 开源协议

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE) 文件

## 👥 联系

- 微信：imjszhang
- X：[JSZHANG](https://x.com/imjszhang)
- 社群：[DataMind Club](https://datamind.club)
- 邮箱：zhangjingsong@helixlife.cn
- 团队：[Helixlife AI Lab](https://github.com/helixlife-ai)

## 🙏 致谢

感谢以下开源项目：
- [Sentence-Transformers](https://github.com/UKPLab/sentence-transformers)
- [FAISS](https://github.com/facebookresearch/faiss)
- [DuckDB](https://github.com/duckdb/duckdb)
