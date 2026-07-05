# Macast-Han 项目上下文

**最后更新**: 2026-07-05
**作者**: Han
**性质**: 基于 xfangfang/Macast 的二次开发（非官方更新）

---

## 项目定位

Macast-Han 是基于 [xfangfang/Macast](https://github.com/xfangfang/Macast)（最后更新 2022 年）的二次开发项目，是一款**跨平台投屏接收与发送应用**。

核心功能：
1. **接收投屏**: 作为 DLNA Renderer，接收手机/其他设备的投屏
2. **发送投屏**: 将本地媒体文件投屏到局域网设备
3. **链接投屏**: 解析媒体链接并投屏

## 与原项目的关系

- **原项目**: xfangfang/Macast（Python + pystray，2022 年停更）
- **Macast-Han**: Tauri 2.0 + Rust 桥接 + Python Sidecar
- **复用代码**: SSDP、DLNA 协议、MPV 渲染器、UPnP XML
- **废弃代码**: pystray GUI、CherryPy HTTP 服务、插件系统

## 目标用户

- 需要在电脑上接收手机投屏的用户
- 需要将电脑媒体投屏到电视/音箱的用户
- 跨平台用户（Windows + macOS + Linux）

## 竞品参考

| 竞品 | 优势 | 劣势 |
|------|------|------|
| AirPlay | 苹果生态无缝 | 仅限苹果设备 |
| Chromecast | 谷歌生态 | 需要硬件 |
| DLNA 通用方案 | 标准协议 | 体验参差不齐 |
| 原版 Macast | 轻量、跨平台 | UI 老旧、维护停滞 |

## 核心差异化

1. **现代化 UI**: Tauri 2.0 + 系统原生特效
2. **跨平台一致**: Windows/macOS/Linux 统一体验
3. **插件系统**: 支持第三方播放器和协议扩展
4. **轻量级**: 系统托盘应用，资源占用低

## 技术约束

### 必须满足
- 支持 Windows 10/11、macOS 12+、Ubuntu 20.04+
- 支持 DLNA/UPnP 协议
- 系统托盘运行
- 开机自启（可选）

### 期望满足
- 系统原生窗口特效
- 多语言支持（中/英）
- 插件扩展系统
- 自动更新

### 不在范围内
- 视频转码
- DRM 内容支持
- 云端服务
- 移动端应用

## 数据流

```
发送投屏:
  用户选择媒体 → 本地 HTTP 服务 → DLNA 控制点 → 目标设备播放

接收投屏:
  手机发起投屏 → SSDP 发现 → DLNA Renderer → MPV 播放
```

## 开发环境

- **OS**: Windows 11 (主要开发)
- **IDE**: VS Code + Claude Code
- **Python**: 3.11+
- **Node.js**: 18+
- **Rust**: 最新 stable

## 参考资源

- [Tauri 2.0 文档](https://v2.tauri.app/)
- [DLNA/UPnP 规范](https://www.dlna.org/)
- [原 Macast 仓库](https://github.com/xfangfang/Macast)
- [功能规格文档](docs/Macast-Functional-Spec.md)
