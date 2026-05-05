# MemPalace → GenericAgent 强化评估（重评版）

## 核心问题：GA 当前的记忆模型痛点

### GA 现状：Push 模型（显式写入才记住）

```
每轮对话 ──→ 如果不显式调用 start_long_term_update ──→ 永久丢失
                ↓ 显式写入
            manual L1/L2/L3 维护（脆弱，依赖AI主动执行）
```

**具体症状：**
1. **对话蒸发**：10轮对话后只记得最后1轮，前面的上下文全丢
2. **决策失忆**："我上次为什么要那么做？"—没写入memory就无迹可寻
3. **无跨会话关联**："用户3天前提过这个"—除非当时写入了L2
4. **搜索弱**：rg 只能匹配精确关键词，无法搜"类似问题"
5. **手动维护脆弱**：L1 Insight 靠AI记得更新，一旦遗漏=信息永久丢失
6. **无时间线**：不知道什么信息是何时产生的，有效期为多久

### MemPalace 方案：Pull 模型（自动全量捕获 + 按需检索）

```
每轮对话 ──→ 自动存入 ChromaDB (verbatim drawer) ──→ 随时语义检索
                ↓
            L1 自动从 top drawers 生成（不需手动维护）
            KG 自动提取实体关系（人/项目/工具/时间）
```

---

## 一、MemPalace 解决 GA 的什么问题

| # | GA 痛点 | MemPalace 解决方案 | 对应模块 |
|---|---------|-------------------|---------|
| 1 | 对话蒸发，上下文丢失 | **全量 verbatim 存储**，每轮对话自动存为 drawer | palace.py + ChromaDB |
| 2 | 搜索只能精确匹配关键词 | **BM25+向量混合搜索**，语义级检索 | searcher.py |
| 3 | 无实体关系追踪 | **SQLite 知识图谱**，人/项目/工具/时间四维关系 | knowledge_graph.py |
| 4 | 手动L1维护脆弱 | L1 自动从 top drawers 生成 | layers.py |
| 5 | 跨会话无关联 | **跨 Wing 隧道**发现隐藏连接 | palace_graph.py |
| 6 | 可能重复存储 | 写入前相似度≥0.85 拦截 | dedup.py |
| 7 | 无法回答"上次为什么这么做" | 完整决策上下文可回溯 | 全部 |
| 8 | 不知道什么信息还在有效期 | 实体/事实带 valid_from→valid_to 时间窗 | knowledge_graph.py |

---

## 二、集成方案（Constitution 可以改）

### 总体架构变化

```
                  现有 GA                             集成后 GA
           ┌──────────────┐                  ┌──────────────────────┐
  L0       │ META-SOP     │          L0      │ META-SOP             │
  L1       │ Insight索引  │          L1      │ Insight索引 + 自动生成│
  L2       │ global_mem   │          L2      │ global_mem.txt        │
  L3       │ SOPs + 脚本  │          L3      │ SOPs + 脚本            │
  L4       │ raw_sessions │          L4      │ raw_sessions           │
           └──────────────┘                  │                       │
                                             │ ←─ ChromaDB 层 ───→ │
                                             │  verbatim drawers    │
                                             │  全量对话持久化       │
                                             │  混合语义搜索         │
                                             │ ←─ SQLite KG ──────→ │
                                             │  实体关系图谱         │
                                             └──────────────────────┘
```

### Phase 1：全量对话持久化（核心）

```
目标：每轮对话自动存入ChromaDB，GA wakeup 时自动检索相关历史
改动：
  ├── pip install chromadb mempalace
  ├── 新建 memory/palace_bridge.py（GA → MemPalace 适配层）
  ├── 修改 ga.py wakeup 流程：追加"从palace检索最近相关上下文"
  ├── 修改 agentmain.py 每轮结束：追加 drawer 写入
  └── Constitution 修改：允许 ChromaDB 作为 L4+ 存储后端

效果：
  问题："上次处理图片上传时遇到的问题是什么？"
  集成前：❌ 除非当时写入了L2，否则无法回答
  集成后：✅ 语义搜索直达相关对话原文
```

### Phase 2：知识图谱

```
目标：自动追踪实体关系，带时间有效性
改动：
  ├── 新建 memory/knowledge_graph.py（从 MemPalace 移植）
  ├── 设计 GA 实体类型：user/project/tool/sop/preference
  ├── agentmain.py 关键节点追加 KG 记录
  └── wakeup 时加载用户偏好图谱

效果：
  GA 能回答：
  - "这个用户常用哪些工具？"
  - "项目X依赖哪些SOP？"
  - "上次用这个工具是什么时候？"
```

### Phase 3：搜索增强

```
目标：rg 精确搜索 + ChromaDB 语义搜索双层
改动：
  ├── 新建 memory/hybrid_search.py
  ├── 修改 assets/sys_prompt.txt：搜索规则增加语义层
  └── RULES: "语义检索用 hybrid_search，精确用 rg"

效果：
  搜索"处理网页截图的问题" → 匹配到"web_scan 页面解析异常"的对话
  rg 搜索"截图" → 只能精确匹配"截图"二字
```

---

## 三、改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `memory/palace_bridge.py` | **新建** | GA↔MemPalace 适配：自动挖掘对话、搜索、wakeup上下文注入 |
| `memory/knowledge_graph.py` | **新建** | 从 MemPalace 移植的 SQLite KG |
| `memory/hybrid_search.py` | **新建** | BM25+向量双层搜索封装 |
| `memory/dedup.py` | **新建** | 相似度检测 |
| `ga.py` | **修改** | wakeup 流程追加 palace 上下文检索 |
| `agentmain.py` | **修改** | 每轮结束追加 drawer 写入 + KG 记录 |
| `assets/sys_prompt.txt` | **修改** | 搜索规则增加语义层指引 |
| `CONSTITUTION` | **修改** | 第6条：允许 ChromaDB 作为 memory 存储后端 |
| 新增依赖 | chromadb, mempalace, sentence-transformers | |

---

## 四、最终决策（用户确认）

| 决策项 | 结论 |
|--------|------|
| GA Constitution | **不动**。原有L0-L4、file_patch、META-SOP完全保留 |
| MemPalace 定位 | **并行新能力层**，不作为GA内存系统的重构 |
| MemPalace 库 | **直接 pip install mempalace** 复用 |
| 集成方式 | GA ↔ palace_bridge.py ↔ MemPalace (ChromaDB + SQLite KG) |
| 迁移 L4 | 暂不导入，先跑通新对话全量捕获 |

### 架构总图

```
  GA 原有层 (完全不动)          MemPalace 新能力层 (并行新增)
  ┌───────────────────┐       ┌──────────────────────────┐
  │ L0 META-SOP       │       │ ChromaDB                 │
  │ L1 Insight索引    │       │  ├─ verbatim drawers     │
  │ L2 global_mem.txt │       │  └─ 混合语义搜索          │
  │ L3 SOPs + 脚本     │       │ SQLite KG                │
  │ L4 raw_sessions   │       │  └─ 实体关系 + 时间窗口   │
  └───────────────────┘       └──────────────────────────┘
           ↑                            ↑
           │     palace_bridge.py       │
           └──────────┬─────────────────┘
                      │
              agentmain.py (每轮结束写入)
              ga.py (wakeup 检索上下文)
```