# Macast 2.0 开发进度

## 当前阶段: Phase 0 — 项目初始化

**最后更新**: 2026-07-05

---

## 总体进度

| 阶段 | 状态 | 进度 |
|------|------|------|
| Phase 0: 项目初始化 | 🔄 进行中 | 30% |
| Phase 1: 基础架构 | ⏳ 待开始 | 0% |
| Phase 2: 前端 UI | ⏳ 待开始 | 0% |
| Phase 3: 后端功能 | ⏳ 待开始 | 0% |
| Phase 4: 集成优化 | ⏳ 待开始 | 0% |

---

## Phase 0: 项目初始化

### 已完成
- [x] 分析原始 Macast 1.x 代码结构
- [x] 阅读并理解功能规格文档
- [x] 创建 CLAUDE.md 项目指南
- [x] 创建 .claude/memory 记忆系统
- [x] 识别可复用代码模块
- [x] 拆解前后端设计文档
  - [x] `docs/Macast-Frontend-Spec.md` — 前端 UI/UX 方案
  - [x] `docs/Macast-Backend-Spec.md` — 后端 Rust+Python 方案

### 进行中
- [ ] 初始化 Tauri 2.0 项目骨架
- [ ] 配置 Python 后端虚拟环境
- [ ] 设计 Rust ↔ Python 通信协议

### 待开始
- [ ] 配置开发环境文档
- [ ] 创建 CI/CD 配置

---

## 关键里程碑

| 里程碑 | 目标日期 | 状态 |
|--------|----------|------|
| M1: 项目骨架完成 | TBD | ⏳ |
| M2: 基础 UI 可运行 | TBD | ⏳ |
| M3: SSDP 发现可用 | TBD | ⏳ |
| M4: DLNA 投屏可用 | TBD | ⏳ |
| M5: 首个 Beta 版本 | TBD | ⏳ |

---

## 会话记录

### 2026-07-05 — 首次会话
- 完成项目结构分析
- 确定技术栈：Tauri 2.0 + Python
- 创建项目文档体系
- 原始代码最后更新于 2022-01，需要大量现代化改造

### 2026-07-05 — 前后端拆解
- 将原始功能规格文档拆解为两个独立方案
- **前端方案** (Macast-Frontend-Spec.md):
  - Vue 3 + Vite + TypeScript + Pinia
  - Tauri invoke() 命令层定义
  - 组件规格、样式系统、国际化
  - WebView 兼容性约束
- **后端方案** (Macast-Backend-Spec.md):
  - Rust SidecarManager (stdin/stdout IPC)
  - Python Sidecar 入口 + 命令路由器
  - 原始代码复用映射表 (ssdp/protocol/renderer/mpv)
  - 新增 MediaParser + MediaServer
  - 完整通信协议定义
  - PyInstaller 打包流程
