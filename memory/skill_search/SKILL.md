# Skill Search — API 客户端

> 从 10 万+ 技能卡中智能检索最适合当前环境的 skill。

## 架构

```
┌─────────────┐     HTTPS/JSON     ┌──────────────────┐
│  客户端 CLI  │ ──────────────────▶ │  Skill Search    │
│  (本项目)    │ ◀────────────────── │  API Server      │
└─────────────┘                     └──────────────────┘
  • 环境检测                          • 105K+ 技能卡索引
  • 结果格式化                        • 四层漏斗检索引擎
  • 零数据依赖                        • 环境过滤 → 安全标注
                                      → 语义匹配 → 质量排序
```

## 快速开始

```bash
# 设置 API 地址
export SKILL_SEARCH_API="https://your-server.com/api"
export SKILL_SEARCH_KEY="your-api-key"  # 可选

# 搜索
python -m skill_search "python testing"

# 限定类别
python -m skill_search "docker deploy" --category devops

# JSON 输出（适合程序集成）
python -m skill_search "git workflow" --json

# 查看环境信息
python -m skill_search --env

# 查看索引统计
python -m skill_search --stats
```

## 编程接口

```python
from skill_search import search, detect_environment

env = detect_environment()
results = search(query="python testing", env=env, top_k=5)

for r in results:
    print(f"{r.skill.name} (score: {r.final_score:.2f})")
    print(f"  {r.skill.one_line_summary}")
```

## 文件结构

```
skill_search/
├── SKILL.md          # 本文档
└── skill_search/     # Python 包
    ├── __init__.py   # 公开 API
    ├── __main__.py   # CLI 入口
    ├── engine.py     # HTTP 客户端（替代本地检索）
    ├── index.py      # SkillIndex 数据模型
    ├── env_detect.py # 本地环境检测
    └── formatter.py  # 结果格式化输出
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SKILL_SEARCH_API` | API 服务地址 | `https://skill-search.example.com/api` |
| `SKILL_SEARCH_KEY` | API 密钥（可选） | 无 |

## API 协议

### POST /search

请求:
```json
{
  "query": "python testing",
  "env": { "os": "windows", "shell": "powershell", ... },
  "category": "coding",
  "top_k": 10
}
```

响应:
```json
{
  "results": [
    {
      "skill": { "key": "org/repo/skill", "name": "...", ... },
      "relevance": 0.85,
      "quality": 7.2,
      "final_score": 0.78,
      "match_reasons": ["完整短语匹配", "标签匹配: python"],
      "warnings": []
    }
  ]
}
```

### POST /stats

请求: `{}` 或 `{"env": {...}}`

响应:
```json
{
  "total": 105586,
  "safe_count": 98234,
  "categories": { "coding": 45000, "devops": 12000, ... }
}
```