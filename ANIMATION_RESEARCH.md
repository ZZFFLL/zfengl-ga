# HeroUI 前端动效库调研报告

## 当前状态

HeroUI 前端（`frontends/heroui/`）技术栈：
- React 19.2 + HeroUI 3.1 + TailwindCSS 4.3 + Vite 7.3 + TypeScript 5.9
- **零动效库依赖**，所有动画均为手写 CSS `@keyframes` 和 `transition`
- `styles.css` 中有 8 个 `@keyframes` 动画和 3 个 CSS transition
- `App.tsx` 中用 `requestAnimationFrame` + `setTimeout` 手写动画状态机
- HeroUI 组件本身支持 `[data-entering]` / `[data-exiting]` 等状态属性

## 候选库对比

| 库 | 包名 | 版本 | 周下载 | 体积(gzip) | 许可证 | React 19 兼容 |
|---|---|---|---|---|---|---|
| **Motion (Framer Motion)** | `motion` | 12.40.0 | 12M | ~45KB | MIT | ✅ 已支持 |
| **GSAP** | `gsap` | 3.15.0 | 3M | ~27KB(core) | 完全免费(2025起) | ✅ 命令式API，天然兼容 |
| **Auto Animate** | `@formkit/auto-animate` | 0.9.0 | 1M | **~2KB** | MIT | ✅ 零配置 |
| **React Spring** | `@react-spring/web` | ~10.x | 2.5M | ~30KB | MIT | ✅ |
| **tailwindcss-motion** | `tailwindcss-motion` | 1.1.1 | 52K | **~0KB**(纯CSS插件) | MIT | ✅ N/A(纯CSS) |
| **Lottie React** | `lottie-react` | 2.4.1 | 500K+ | ~150KB | MIT | ✅ |

---

## 推荐方案

### 🥇 首选：Motion（原 Framer Motion）

**理由：**
- **HeroUI 官方推荐**，官方文档有专门的 Framer Motion 集成指南，直接 `motion(Button)` 包裹 HeroUI 组件即可
- **API 最符合 React 声明式范式**：`initial` / `animate` / `exit` / `transition` props
- **layout 动画**（自动 FLIP）是杀手级特性：列表重排、折叠展开、尺寸变化自动平滑过渡
- **`AnimatePresence`** 解决挂载/卸载动画：聊天消息、Modal、Toast 等场景必备
- **手势支持**：`whileHover` / `whileTap` / `drag` 一行搞定
- **12M 周下载**，生态最活跃，Framer 公司维护

**适合 HeroUI 的场景：**
```tsx
// 聊天消息入场动画
<motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
  <Card>消息内容</Card>
</motion.div>

// 侧边栏列表自动布局
<motion.div layout>  {/* 列表增删自动平滑过渡 */}

// Toast/Modal 入场退场
<AnimatePresence>
  {showToast && <motion.div exit={{ opacity: 0, y: -20 }}>...</motion.div>}
</AnimatePresence>

// 按钮交互
<MotionButton whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
  发送
</MotionButton>
```

**安装：**
```bash
cd frontends/heroui && pnpm add motion
```

**体积优化：** 支持 tree-shaking，从 `motion/react` 按需导入可压缩到 ~30KB。

---

### 🥈 轻量补充：Auto Animate

**理由：**
- **2KB**，几乎零成本
- **一行代码**给任意列表/容器加上移动/添加/删除动画：`useAutoAnimate(ref)`
- 适合给 Session 列表、消息列表、文件列表快速加动效
- 不冲突，可与 Motion 共存

**适合 HeroUI 的场景：**
```tsx
const [ref] = useAutoAnimate<HTMLDivElement>();
<div ref={ref}>
  {sessions.map(s => <SessionItem key={s.id} />)}  {/* 增删自动动画 */}
</div>
```

**安装：**
```bash
cd frontends/heroui && pnpm add @formkit/auto-animate
```

---

### 🥉 可选：GSAP（复杂场景）

**理由：**
- 2025 年起**完全免费**（含所有付费插件），Webflow 收购后开源
- **时间线动画**最强：多步骤编排、滚动驱动动画
- 核心包仅 **27KB gzip**（不含插件）
- 命令式 API，天然兼容 React 19

**适合 HeroUI 的场景：**
- 输入框聚焦时的光标呼吸动画
- Agent 运行时的复杂进度指示器
- 滚动驱动的消息列表视差效果

**注意：** GSAP 是命令式 API，需要 `useRef` + `useEffect`，与 React 声明式模型有摩擦。仅在 Motion 无法满足的复杂编排场景时引入。

**安装：**
```bash
cd frontends/heroui && pnpm add gsap
```

---

### 🏷️ 备选：tailwindcss-motion

**理由：**
- 纯 TailwindCSS 插件，**零 JS 体积增加**
- 直接用 class 写动画：`motion-translate-x-100 motion-duration-500`
- 适合给现有 CSS transition 补充更丰富的内置动画预设

**适合 HeroUI 的场景：**
- 快速给 HeroUI 组件加 hover/focus 动效
- 替代 `styles.css` 中手写的 `@keyframes`

**安装：**
```bash
cd frontends/heroui && pnpm add -D tailwindcss-motion
```
在 CSS 中 `@import "tailwindcss-motion";`

---

## 实施建议

### 阶段一：核心动效（推荐先做）
安装 `motion` + `@formkit/auto-animate`：
```bash
cd frontends/heroui && pnpm add motion @formkit/auto-animate
```

优先改造：
1. **聊天消息入场**：新消息淡入 + 上滑
2. **Session 列表**：`useAutoAnimate` 一行搞定增删动画
3. **侧边栏展开/折叠**：`layout` 动画
4. **Toast/通知**：`AnimatePresence` 入退场
5. **按钮交互**：`whileHover` / `whileTap` 缩放反馈
6. **加载状态**：骨架屏 pulse 或 spinning 指示器

### 阶段二：进阶动效（按需）
- 复杂进度动画 → GSAP
- Lottie JSON 动画（设计师提供）→ `lottie-react`
- 更多 Tailwind 动画预设 → `tailwindcss-motion`

### 性能注意
- 动画只用 `transform` 和 `opacity`（GPU 加速），避免 `width`/`height`/`left`/`top`
- 使用 HeroUI 的 `motion-reduce:` 变体尊重用户 `prefers-reduced-motion` 设置
- `AnimatePresence` 只包裹需要退出动画的元素，避免不必要渲染
