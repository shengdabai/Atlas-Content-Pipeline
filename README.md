# Atlas Content Pipeline — 知识库到网站的内容 ETL 管道

> **一键将知识库笔记转换为结构化网站文章** — 自动解析、分类、验证 GetNote 导出的 Markdown 笔记，生成符合 Astro 前端 Schema 的文章文件。

[![CI](https://github.com/shengdabai/atlas-content-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/shengdabai/atlas-content-pipeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## 产品简介

Atlas Content Pipeline 是一个面向内容创作者和教育平台开发者的知识管理 ETL 工具。它从 GetNote 知识库导出的 Markdown 文件出发，自动完成内容解析、分类评分、LLM 推理 frontmatter、本地验证、输出为结构化文章文件的全流程。

**适合谁用：**
- 教育平台开发者：批量将教学笔记转为网站文章
- 内容创作者：结构化整理知识库内容
- 个人博客作者：自动化内容分类和标签管理

## 核心功能

- **自动解析**: 从 GetNote Markdown 导出中提取独立笔记条目
- **智能评分**: 基于关键词权重的 P0 启动内容筛选（HSK 1-3 优先）
- **LLM 推理**: 调用 Claude API 自动生成分类、HSK 级别、标签、摘要
- **本地规则引擎**: 无需 API Key 的启发式模式，零成本运行
- **本地验证**: JSON Schema 严格校验，单条失败不影响整体运行
- **结构化输出**: 分类目录 + Markdown 文件 + manifest JSON + 跳过列表
- **配置设计参考**: 提供 `config.yaml.example`；配置文件加载尚未实现

## 技术架构

```
GetNote Export → Parser → Score → LLM Inference → Validator → Article Files
                                                        ↓
                                            category/hsk-tags-summary.md
```

### Provider 模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `anthropic-api` | 直接调用 Anthropic Messages API | 有 API Key，需要 LLM 推理 |
| `claude-cli` | 本地 Claude CLI 封装 | 已安装 Claude CLI |
| `heuristic` | 本地规则引擎 | 无凭证，验证管道流程（推荐入门） |

## 快速开始

### 环境要求

- Python 3.9+
- `ANTHROPIC_API_KEY` 环境变量（使用 LLM 模式时）

### 运行示例

默认从当前目录的 `input/getnote-export.md` 读取，写到 `output/pilot`。
可以通过 `--source` 和 `--output-dir` 指定其他位置。

```bash
# Dry-run：解析 + 选择候选（不写入文件）
python3 scripts/getnote_frontmatter_pipeline.py --dry-run --limit 30

# Heuristic 模式：30 条试点运行（无需 API Key）
python3 scripts/getnote_frontmatter_pipeline.py \
  --provider heuristic --limit 30 --selection p0-seed

# LLM 模式：30 条试点 + Claude 推理 frontmatter
python3 scripts/getnote_frontmatter_pipeline.py \
  --provider anthropic-api --limit 30 --selection p0-seed \
  --model claude-sonnet-4-0

```

`config.yaml.example` 目前仅作配置设计参考；脚本尚不支持 `--config`。

### 容器运行

容器默认显示帮助后退出。它是一次性批处理工具，没有 HTTP 端口和常驻健康检查。
把输入目录以只读方式挂载，显式指定输出目录，例如：

```bash
docker run --rm -v "$PWD/input:/data:ro" -v "$PWD/output:/output" \
  atlas-content-pipeline --source /data/getnote-export.md \
  --output-dir /output --provider heuristic --limit 30
```

## 输出格式

```text
output/pilot/
├── hsk-prep/
│   └── hsk3-course-explanation-record.md
├── learn-chinese/
│   └── chinese-time-expressions.md
├── manifests/
│   ├── pilot-manifest.json
│   └── skipped.json
```

每篇文章包含验证过的 frontmatter：

```yaml
---
category: learn-chinese
hsk_level: 2
tags: ["时间", "日常表达"]
summary: 中文时间表达方式的完整指南
audience: 初学者
intent: 学习
pilot_priority: high
---
```

## 定价

| 计划 | 价格 | 功能 |
|------|------|------|
| 开源版 | ¥0 | 完整功能，支持 heuristic + LLM 模式 |
| SaaS 版 | ¥99/月 | 云端托管 + 多知识库 + API 集成 + Notion/Obsidian 支持 |

> 当前为开源免费工具，SaaS 版规划中。

## 项目结构

```
atlas-content-pipeline/
├── README.md                              # 项目说明
├── index.html                             # 落地页 HTML
├── config.yaml.example                    # YAML 配置文件示例
├── schema/
│   └── article-frontmatter.schema.json    # JSON Schema 定义
├── scripts/
│   └── getnote_frontmatter_pipeline.py    # 主脚本 (878 行, 30 个函数)
├── tests/
│   └── test_pipeline.py                   # 单元测试 (覆盖解析/评分/验证/heuristic)
├── output/
│   ├── manifests/                         # manifest JSON
│   └── pilot/                             # 输出文章
└── .github/
    ├── FUNDING.yml                        # 赞助配置
    └── workflows/
        └── ci.yml                         # GitHub Actions CI
```

## 技术特点

- **零外部 Python 依赖**: 仅使用 urllib 直接调用 HTTPS API
- **严格本地验证**: Slug 本地生成，不信任模型输出
- **容错设计**: 单条笔记失败不影响整体运行
- **内容溯源**: 保留原始出处，模型只做分类和摘要
- **单元测试覆盖**: 核心模块（解析、评分、验证、启发式推理）均有测试

## 路线图

- [ ] 支持 Notion/Obsidian 知识库导出格式
- [ ] 完整的 YAML/TOML 配置文件加载
- [ ] 更多 ETL 源格式支持
- [ ] SaaS 版本原型设计

## 支持项目

如果这个工具对你有帮助，欢迎 [赞助支持](https://github.com/sponsors/shengdabai) ☕

---

**Atlas Content Pipeline** — 一键将知识库笔记转换为结构化网站文章
