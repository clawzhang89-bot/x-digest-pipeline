# X Digest 主稿调研指南

目标：把 X 上发现的主题，扩展成适合 8~12 分钟播客口播的主稿，而不是只做社交媒体摘要。

## 总原则

X 负责发现线索，但主稿不能只依赖 X。

主稿必须在以下两类信息之间建立平衡：

1. **源头信息**：产品到底是什么、变了什么、官方怎么定义这件事
2. **外部反应**：行业如何理解、争议点在哪里、为什么这件事重要

如果只有 X 帖子，稿子容易碎、短、浅。
如果只有官方材料，稿子容易像产品说明书。
要把两者结合起来。

## 调研优先级

### 第一优先级：源头信息
优先补：
- 官方 blog
- 官方 docs
- GitHub repo
- release notes / changelog
- 产品页
- 官方 demo / 发布说明
- 创始人 / 官方账号原话

适用问题：
- 产品到底是什么？
- 这次更新具体改了什么？
- 和之前版本相比变化在哪里？
- 官方想把它定义成什么？

### 第二优先级：X 搜索
用于补：
- 及时性
- 社区反应
- 分歧点
- 用户 / 开发者反馈
- 哪些人最早抓住重点

适用问题：
- 行业内最先怎么理解这件事？
- 有哪些关键争议？
- 哪些评价说明这件事真的重要？

### 第三优先级：高质量二手材料
作为辅助：
- 高质量媒体报道
- 可靠分析博客
- 采访整理
- 播客节目摘录

适用问题：
- 补背景
- 找更完整的上下文
- 建立对照视角

## 主稿研究流程

### 1. 从 X 发现线索
从 watchlist 与 topic planning 中找出当天最值得深挖的一个主题。

### 2. 明确主问题
在调研前先问清楚：
- 这篇稿子真正要回答什么？
- 为什么这件事值得讲 10 分钟？
- 它是产品更新、行业趋势，还是观点对撞？

### 3. 回源头补事实
至少补到能回答：
- 这次更新 / 发布的核心内容是什么
- 和过去相比新增了什么
- 官方最看重的变化是什么

### 4. 用 X 搜索补反应
补这些维度：
- 谁在讨论它
- 哪些观点彼此印证
- 哪些观点明显冲突
- 用户/开发者的真实反馈是什么

### 5. 再决定文章结构
基于材料判断更适合：
- 事件推进型
- 主题综述型
- 观点对撞型

### 6. 最后成文
成文时要把：
- 事实层
- 变化层
- 争议层
- 影响层
串成一条主线

## 主稿与快报的区别

### 主稿
- 每天至少 1 篇
- 长度目标：适合 8~12 分钟口播
- 必做 research enrichment
- 要有源头信息 + 外部反应
- 对于视频生成、多模态模型这类赛道，默认建立头部对照池，至少覆盖 OpenAI、Google DeepMind、Runway、Luma、Pika、Seedance、Kling、MiniMax 等主要玩家中的相关方

### 快报
- 若干条
- 长度短
- 不做重 research，或只做最少量补充
- 用于覆盖次重要主题

## 研究边界

为了保证谨慎，主稿默认优先使用高可信来源：
- 官方文档
- 官方博客
- GitHub
- 产品页面
- 创始人 / 核心人物原话
- 知名高质量媒体

谨慎使用：
- 无来源的二手总结
- 情绪化评论
- 转载号
- 没法确认事实链条的内容

## 关键要求

凡是涉及：
- 产品是什么
- 改了什么
- 和之前有什么差别

优先回到源头，不依赖转述。

## enrichment 层新增要求

在 `research_enrichment` 阶段，不要只吐搜索词。至少要先把 seed 文章拆成：
- 一句话主题
- 核心论点
- 3~5 个关键 claims
- 当前内容薄弱点（背景 / 事实 / 反方 / 时间线 / 行业格局）
- 适合交给 Perplexity 的 research questions

这些 questions 要覆盖：
- 事实核验
- 历史时间线
- 支持证据
- 反方与限制
- 竞争格局 / 关键参与者
- 未来观察点

## 当前落地后的使用方式

### 1. 先生成 research brief

```bash
cd /Users/admin/.openclaw/workspace/x-digest
python3 research_enrichment.py
```

输出：
- `data/research_enrichment.json`

至少包含：
- 主题摘要
- core claim
- key claims
- content gaps
- research questions

### 2. 再生成 research materials / evidence pack

```bash
cd /Users/admin/.openclaw/workspace/x-digest
python3 research_collect.py
```

当前会同时调用：
- Perplexity Search API
- Perplexity Sonar

输出：
- `data/research_materials.json`

其中包含：
- `perplexity.results`：Search API 原始检索结果
- `perplexity.sonar`：Sonar 的结构化研究返回
- `evidence_pack`：归一化后的写作输入层

### 3. 再生成带 research pack 的写作请求

```bash
cd /Users/admin/.openclaw/workspace/x-digest
python3 write_editorial_digest.py --all-plans
```

这样就算 topic 被 gate 判成 skip，也能手动生成带 research pack 的 request。

## evidence_pack 的当前目标结构

`evidence_pack` 当前至少包含：
- `executive_summary`
- `timeline`
- `evidence_for`
- `evidence_against`
- `landscape`
- `open_questions`
- `source_buckets`
- `citations`

并且已经过：
- normalization
- 去重
- 限长
- schema hardening

## 后续实现建议

后续继续迭代时，优先围绕：
- claim-evidence 对齐
- official source 优先级提升
- 反方材料补全
- timeline 校正
- evidence pack 独立文件化（便于后续审计 agent 消费）
