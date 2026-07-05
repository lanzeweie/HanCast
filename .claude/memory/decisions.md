# Macast 2.0 架构决策记录

**最后更新**: 2026-07-05

---

## 决策日志

### DEC-001: 前端框架选择
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 使用 Tauri 2.0 作为前端框架
- **理由**:
  - 跨平台支持（Windows/macOS/Linux）
  - 系统原生 WebView，打包体积小
  - Rust 后端性能优秀
  - 支持系统窗口特效（Mica/Vibrancy）
- **替代方案**: Electron（体积大）、Flutter Desktop（生态不成熟）

### DEC-002: 后端语言保留 Python
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 保留 Python 作为后端服务语言
- **理由**:
  - 原始代码为 Python，可复用
  - DLNA/SSDP 协议库成熟
  - 开发效率高
- **风险**: Python 进程管理需要 Rust 层处理

### DEC-003: 前端不做媒体解码
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 前端仅做 UI，所有媒体处理交给后端
- **理由**:
  - 避免 WebKit vs Chromium 解码兼容性问题
  - macOS WebKit 对某些格式支持有限
  - 统一后端处理逻辑更易维护

### DEC-004: 窗口特效策略
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 使用 tauri-plugin-vibrancy 实现跨平台特效
- **方案**:
  - Windows: Mica / Acrylic
  - macOS: Vibrancy
  - Linux: 无特效，纯色背景

### DEC-005: Rust ↔ Python 通信方式
- **日期**: 2026-07-05
- **状态**: 🔄 待验证
- **决策倾向**: HTTP REST API
- **理由**:
  - 调试方便
  - Python 生态支持好
  - 可选 WebSocket 用于实时状态推送
- **替代方案**: stdin/stdout IPC、gRPC

---

## 待决策事项

### PENDING-001: Python HTTP 框架
- **选项**: CherryPy（原版） vs FastAPI vs aiohttp
- **倾向**: FastAPI（现代、async、类型安全）
- **阻塞因素**: 需评估原 CherryPy 代码迁移难度

### PENDING-002: 前端 UI 框架
- **选项**: 纯 HTML/CSS vs Vue 3 vs React
- **倾向**: Vue 3 + Vite
- **阻塞因素**: 需确认 Tauri 2.0 最佳实践

### PENDING-003: 状态管理方案
- **选项**: Pinia vs Zustand vs 自定义
- **倾向**: Pinia（Vue 官方推荐）
- **阻塞因素**: 取决于前端框架选择

### PENDING-004: 打包与分发策略
- **选项**: PyInstaller 嵌入 vs 独立 Python 进程
- **倾向**: 独立进程 + 自动启动
- **阻塞因素**: 需测试各平台兼容性
