# X Digest 分类规则

这个项目用于跟踪 X（Twitter）账号，并按主题分组，后续做增量抓取与每日摘要。

## 分类原则

- **允许重复归类**：一个账号可以属于多个分类
- 优先按账号近一年主要内容归类
- 如果一个账号明显跨主题，可以同时放进多个分类
- 先求可用，不追求学术上绝对精确
- 后续可以继续细分，但当前先维持 3 个核心组

## 当前分类

### 1. ai_llm
适合放：
- foundation model
- LLM
- reasoning
- training / finetuning
- evals
- inference infra
- AI 产品与模型平台

### 2. embodied_vla_world_model
适合放：
- robotics
- embodied AI
- VLA
- world model
- simulation
- robot policy / manipulation
- 自动驾驶里偏世界建模、控制、机器人智能的内容

### 3. agents_automation
适合放：
- AI agents
- coding agents
- browser agents
- workflow automation
- tool use
- Claude Code / Coworker / OpenClaw / MCP / automation agent infra

## 输出建议

后续维护同时保留两种视图：

1. **按组输出**
2. **按账号输出标签**

例如：

- `karpathy -> ai_llm, agents_automation`
- `AnthropicAI -> ai_llm, agents_automation`
- `Figure_robot -> embodied_vla_world_model`

## 维护规则

- 新账号先人工归类
- 不确定时允许放进多个组
- 如果一个账号长期偏离原主题，再调整分组
- 避免过度设计；先服务于“每日订阅摘要”这个目标
