# x-digest

最小测试项目：用 X 官方 API 抓取公开账号最近 posts。

## 前提

环境变量里已有：

```bash
X_BEARER_TOKEN
```

如果刚写到 `~/.zshrc`，先执行：

```bash
source ~/.zshrc
```

## 测试脚本

### 1) 单独测试几个账号

```bash
python3 fetch_test.py naval sama
```

也支持带 `@`：

```bash
python3 fetch_test.py @naval @sama
```

### 2) 从 watchlist 批量抓取

默认读取 `watchlist.seed.json`：

```bash
python3 fetch_watchlist.py
```

指定文件：

```bash
python3 fetch_watchlist.py ./watchlist.seed.json
```

指定抓取条数（默认每个账号 5 条）：

```bash
python3 fetch_watchlist.py ./watchlist.seed.json 5
```

### 3) 增量抓取（正式骨架）

默认读取正式版 `watchlist.json`：

```bash
python3 fetch_incremental.py
```

也可以指定：

```bash
python3 fetch_incremental.py ./watchlist.json ./state.json ./data/latest_incremental.json
```

## 输出内容

脚本会输出 JSON，包括：

- user.id
- user.name
- user.username
- groups
- posts[].id
- posts[].created_at
- posts[].text
- posts[].url
- posts[].public_metrics

`fetch_watchlist.py` 还会额外输出：

- `accounts`：按账号聚合的抓取结果
- `groups`：按分组聚合的抓取结果

`fetch_incremental.py` 会额外维护：

- `state.json`：记录每个账号的 `user_id`、`since_id`、`last_checked_at`
- `data/latest_incremental.json`：最近一次增量抓取结果

默认：
- 每个账号抓最近 5 条（批量测试脚本）
- 增量脚本默认每次抓最近最多 10 条新内容
- 排除 replies
- 保留转推 / 引用推文（后面可以再细分）

## 分类与种子名单

项目里新增了：

- `CATEGORIES.md`：分类规则与归类原则
- `watchlist.seed.json`：初始种子名单（每组至少 10 个头部账号，允许重复归类）
- `watchlist.json`：正式关注列表（后续优先维护这个文件）

当前核心分类：

1. `ai_llm`
2. `embodied_vla_world_model`
3. `agents_automation`

## 内容输出与索引

项目里新增了：

- `EDITORIAL_GUIDE.md`：成文原则与记者式整理要求（已纳入时间线、人名称谓、轻问候语/收束语规范）
- `SERIES_POLICY.md`：跨日联动、主题去重、系列文章策略
- `topic_planner.py`：根据新增材料和最近文章，生成主题规划（新主题 / follow-up）
- `publish_gate.py`：发布阈值判断（发布 / 跳过），避免重复出文
- `article_index.schema.json`：文章索引元数据结构
- `write_editorial_digest.py`：生成“记者式成文”的写作请求包
- `generate_digest.py`：把增量抓取结果整理成 Markdown 文章，并写入索引 README + JSON 索引
- `run_digest_pipeline.py`：统一入口脚本，串起抓取、规划、发布判断、写作请求和文章输出

默认输出目录：

- `articles/YYYY-MM-DD/*.md`
- `articles/README.md`
- `articles/index.json`
- `editorial_requests/*.json`
- `reports/YYYY-MM-DD.md`
- `reports/latest.md`

## 统一运行

直接跑整条流水线：

```bash
cd /Users/admin/.openclaw/workspace/x-digest
python3 run_digest_pipeline.py
```

可选参数：

```bash
python3 run_digest_pipeline.py --watchlist ./watchlist.json --state ./state.json --incremental ./data/latest_incremental.json
python3 run_digest_pipeline.py --skip-fetch
python3 run_digest_pipeline.py --skip-plan
python3 run_digest_pipeline.py --skip-gate
python3 run_digest_pipeline.py --skip-request
python3 run_digest_pipeline.py --skip-generate
python3 run_digest_pipeline.py --report-only
```

`--report-only` 会只跑到 topic planning + publish gate，然后输出一份报告，并落盘到：
- `reports/YYYY-MM-DD.md`
- `reports/latest.md`

报告会告诉你：
- 今天有哪些主题候选
- 每个候选是 publish 还是 skip
- skip 的原因是什么

## 下一步

后续可以在这个项目上继续加：

1. 把当前规则接入更强的自动化大模型成文流程
2. 自动按主题拆成多篇，而不是固定按组输出
3. sqlite 存储
4. Telegram 推送
5. 定时任务调度
