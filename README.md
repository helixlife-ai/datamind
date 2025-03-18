# DataMind

## ⚗️ Your AI-Powered Data Alchemy Cauldron, Turning Documents into Golden Insights

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org)
[![Node.js](https://img.shields.io/badge/Node.js-20.x-green.svg)](https://nodejs.org/)
[![Version](https://img.shields.io/badge/version-0.3.0-green.svg)](https://github.com/helixlife-ai/datamind/releases)

[English](README.md) | [中文](docs/README_zh.md)

## 📖 Introduction

Welcome to the magical world of data alchemy! DataMind is an AI-powered knowledge cauldron that unearths hidden insights behind your data.

**Data in, Surprise out!**

DataMind helps you transform any document into shining crystals of wisdom:
- Put in raw documents, get refined knowledge essence
- Add information fragments, receive coherent complete wisdom
- Insert messy data, obtain clear intuitive insights
- Inject complex problems, extract concise elegant solutions

Whatever challenges you face:
- Need deep market insights? Put in industry reports and news articles — harvest a comprehensive market landscape analysis
- Building complex technical documentation? Add codebase and API docs — get a perfectly structured technical manual
- Analyzing competitor movements? Input competitor data and social information — receive a precise competitive landscape map
- Planning your next project? Place historical files and requirement lists — display a well-organized project blueprint

Like a magic stone turning ordinary into gold, DataMind will complete the magical transformation from ordinary data to shining wisdom:
- Applies cutting-edge AI technology to understand document meanings
- Precisely comprehends your every natural language request
- Automatically generates professional, coherent analysis reports
- Presents final products in your preferred format
- Ensures every output is both logical and factually accurate

Put in your data, state your needs, and let DataMind's AI magic craft the perfect answer!

## ✨ Core Features

### 🎨 New Features (v0.3.0)
- First official release version

## 🚀 Quick Start

### Installation

```bash
# Clone the project
git clone https://github.com/helixlife-ai/datamind.git
cd datamind

# Install Python dependencies
pip install -r requirements.txt
playwright install chromium

# Generate test data
python scripts/generate_test_data.py

# Install Node.js (if not already installed)
# For Ubuntu/Debian:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# For MacOS (using Homebrew):
brew install node@20

# For Windows:
# Please download and install Node.js 20.x version from https://nodejs.org/en/download/

# Install pnpm (if not already installed)
npm install -g pnpm
```

### Usage Example

The easiest way to get started is to run the example script:

```bash
# Run the app
cd app
pnpm install
node server.js
```
Open in browser: http://localhost:3000
Place your local documents in the work_dir directory, then click the start button.

## ⚙️ Configuration

### Environment Variables

The project uses environment variables for configuration. You can set them up in two ways:

1. Using `.env` file (recommended):
   ```bash
   cp .env.example .env
   # Then edit .env with your values
   ```

2. Setting directly in environment with your large language model (Claude3.7 recommended, DEEPSEEK alternative):
   ```bash
   DEFAULT_API_KEY=["your-api-key-here"]
   DEFAULT_BASE_URL=https://api.anthropic.com/v1
   DEFAULT_GENERATOR_MODEL="claude-3-7-sonnet-20250219"
   DEFAULT_REASONING_MODEL="claude-3-7-sonnet-20250219"
   ```

## 🤝 Contributing

PRs and Issues welcome! See [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is under MIT License - see [LICENSE](LICENSE) file

## 👥 Contact

- WeChat: imjszhang
- X: [JSZHANG](https://x.com/imjszhang)
- Community: [DataMind Club](https://datamind.club)
- Email: zhangjingsong@helixlife.cn
- Team: [Helixlife AI Lab](https://github.com/helixlife-ai)

## 🙏 Acknowledgments

Thanks to these open source projects:
- [Sentence-Transformers](https://github.com/UKPLab/sentence-transformers)
- [FAISS](https://github.com/facebookresearch/faiss)
- [DuckDB](https://github.com/duckdb/duckdb)