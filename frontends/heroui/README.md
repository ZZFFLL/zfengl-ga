# GenericAgent HeroUI

Stage 1 frontend for GenericAgent. Bridge runs the agent (Python aiohttp on
:14169), this UI streams tokens / events from it (Vite on :5178).

## 启动方式一览

| 入口 | 命令 | 平台 | 何时用 |
|---|---|---|---|
| Makefile（推荐） | `make start` | macOS / Linux | 日常开发、CI 脚本 |
| pnpm | `pnpm heroui-start` | 跨平台 | 没有 `make` 时 |
| Finder 双击 | 双击 `start.command` | macOS | 不想开终端 |
| Explorer 双击 | 双击 `start.cmd` | Windows | Windows |
| bash 直接跑 | `bash start.command` | 跨平台 | +x 被外部抹掉时的兜底 |
| 分进程手动 | `make dev` + `make bridge` | 跨平台 | 调试、看日志 |

> **统一保证**：所有 `start` 入口都先 `chmod +x start.command start.cmd`。
> 即使 +x 被 git / Finder / quarantine 抹掉，下次启动会自愈回来。

## 一键启动

macOS / Linux：

```bash
cd frontends/heroui
make start
# 或：pnpm heroui-start
```

Windows：

```cmd
cd frontends/heroui
start.cmd
```

启动后：

- 桥服务: <http://127.0.0.1:14169>
- UI: <http://127.0.0.1:5178>

## 停止 / 状态

```bash
make stop          # 杀掉 14169/5178 上的进程 + 残留 Vite 端口
make status        # 看谁占着端口
# 或：
pnpm heroui-stop
pnpm heroui-status
```

## 分进程跑（调试时）

```bash
# 终端 1：桥
cd frontends/heroui
make bridge        # 或 python3 bridge.py

# 终端 2：UI
cd frontends/heroui
make dev           # 或 pnpm dev
```

## 单组件 / 工具

```bash
make dev        # 只跑 Vite
make bridge     # 只跑 Python 桥
make install    # pnpm install --prefer-offline
make chmod      # 单独修 +x（一般不用，start 入口会自动修）
make help       # 所有 target 列表
```

## 配置

默认桥地址 `http://127.0.0.1:14169`，可覆盖：

```bash
HEROUI_BRIDGE_PORT=14169 \
VITE_GA_HEROUI_API_TARGET=http://127.0.0.1:14169 \
pnpm dev
```

## 构建静态包

```bash
pnpm build
```

## +x bit 为何会丢 / 为什么这套启动方式不会再出问题

**根因**：`core.fileMode=false` 在父仓库多层配置都是 false，git 完全不感知
文件模式变化，所以 `start.command` / `start.cmd` 一直是 100644，每次
`git pull` 后 +x 都不回来。

**修复**（commit `fe3ab82`）：

1. **git 跟踪** — `frontends/heroui/.git/config` 设 `core.fileMode=true`
   （只影响此子目录），两个启动脚本都以 100755 模式提交。`git pull` / 切分支 /
   克隆后 +x 自动恢复。
2. **`start.command` 自愈** — 脚本顶部有
   `[ -x "$0" ] || chmod +x "$0"`，任何成功启动都会重新打上 +x，让
   Finder 双击下次也好用。
3. **Makefile / pnpm 入口兜底** — `make start` / `pnpm heroui-start` 每次
   先 `chmod +x`，再 `bash start.command`（bash 启动不需要 +x），触发自愈。

所以即使外部 `chmod 644`、Finder Get Info、macOS quarantine 再次抹掉 +x，
下次启动一定能跑、并把 +x 修回去。
