# Plan Mode SOP

> 简单任务（1-2步可完成）无需本SOP，直接做。

## 0. 基本协议

进入 plan mode 后，立即调用 `update_working_checkpoint`，内容包含：

1. **PLAN**：初始为 `[ ] 规划` `[ ] 执行`，规划完成后展开为详细 checklist
2. **RULES**（以下三条原文写入，每次 update 必须保留）：
   - 一次只做一步，完成后标 [x] 并 update checkpoint
   - 每次 checkpoint 必须保留完整 PLAN + RULES
   - 全部 [x] 才可收尾

## 1. 规划阶段

初始 checkpoint：`[ ] 规划` `[ ] 执行`。"规划"完成 = 展开执行步骤并 update checkpoint。

### 1a. 读 SOP
查 insight 找相关 SOP 并读取——SOP 提供任务骨架，直接指导分解。无则跳过。不确定性最高的环节先探，其结果可能推翻整个计划。

### 1b. 分类
从依赖关系读出结构：有依赖→Sequential | 无依赖→MapReduce | 条件未知→Branch。可嵌套。

### 1c. 分解
按结构展开 checklist（每步须有独立完成判据，否则继续拆）。update checkpoint 并标 `[x] 规划`。
- Seq: `[ ]A → [ ]B → [ ]C`
- MR: `MAP: [ ]D1 [ ]D2 … REDUCE: [ ]汇总`
- Branch: `[ ]尝试X → 成功:[ ]Y / 失败:[ ]Z`

## 2. 执行注意

- 计划有误时回到规划修正，不硬凑；不可逆操作前多验证一步
- MapReduce 的 MAP 可用 subagent 并行执行
- 步骤间用尽量用文件传递中间结果和汇总，不靠上下文记忆
- 收尾：全部 `[x]` 后汇总结果，清理 checkpoint