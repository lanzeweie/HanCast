# HanCast 2.0 — 前端设计规格

> **文档性质**: Tauri 2.0 前端 UI/UX 专属方案
> **对应层级**: WebView 层 + Rust Tauri 壳层
> **不涉及**: Python 后端内部实现、DLNA 协议细节

---

## 1. 前端技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 应用框架 | Tauri 2.0 | 跨平台桌面壳 |
| UI 渲染 | WebView2 (Win) / WebKit (Mac) / WebKitGTK (Linux) | 系统内置 |
| 前端框架 | Vue 3 + Vite | Composition API |
| 类型系统 | TypeScript | 严格模式 |
| 状态管理 | Pinia | Vue 官方推荐 |
| 样式方案 | CSS Variables + Scoped CSS | 主题切换 |
| 国际化 | vue-i18n | 中/英/繁 |

### 1.1 WebView 引擎差异

| 平台 | 引擎 | CSS 限制 | JS 限制 |
|------|------|----------|---------|
| Windows 10/11 | WebView2 (Chromium 110+) | 几乎无限制 | 完整 ES2022 |
| macOS 12+ | WebKit (Safari 16+) | 部分新特性缺失 | ES2022 大部分 |
| Linux | WebKitGTK 4.0+ | 较保守 | ES2020 基线 |

**兼容性规则**:
- 所有 CSS 必须通过 `@supports` 检测或使用基线特性
- 避免依赖 Chromium 独有 API
- 使用 Polyfill 填补 WebKitGTK 差距
- 测试矩阵：每个组件必须在三个引擎下验证

---

## 2. 窗口配置

### 2.1 Tauri 窗口参数

```jsonc
// tauri.conf.json → app.windows[0]
{
  "title": "HanCast",
  "width": 420,
  "height": 600,
  "minWidth": 360,
  "minHeight": 480,
  "maxWidth": 800,
  "maxHeight": 900,
  "resizable": true,
  "decorations": false,       // 无边框，自定义标题栏
  "transparent": true,        // 透明背景，支持系统特效
  "center": true
}
```

### 2.2 系统窗口特效

| 平台 | 特效 | 实现方式 |
|------|------|----------|
| Windows 11 | Mica (云母) | `tauri-plugin-mica` |
| Windows 10 | Acrylic (亚克力) | `tauri-plugin-mica` 降级 |
| macOS | Vibrancy (果冻) | `tauri-plugin-vibrancy` |
| Linux | 无特效 | CSS 纯色背景兜底 |

**Rust 壳层代码** (仅窗口特效，不含业务逻辑):
```rust
// src-tauri/src/window_effect.rs

#[cfg(target_os = "windows")]
pub fn apply(window: &tauri::Window) {
    // 尝试 Mica，失败则降级 Acrylic
    if window.apply_mica(true).is_err() {
        window.apply_acrylic(None).ok();
    }
}

#[cfg(target_os = "macos")]
pub fn apply(window: &tauri::Window) {
    window.apply_vibrancy(
        tauri_plugin_vibrancy::NSVisualEffectState::Active,
        None, None
    ).ok();
}

#[cfg(target_os = "linux")]
pub fn apply(_window: &tauri::Window) {
    // 无系统特效，前端 CSS 兜底
}
```

---

## 3. 前端 ↔ 后端交互

> 完整的三层通信协议定义见 [HanCast-Backend-Spec.md §2 交互层定义](./HanCast-Backend-Spec.md#2-交互层定义-三层通信)

### 3.1 前端视角的调用链

```
Vue 组件  →  api/commands.ts  →  Tauri invoke()  →  Rust  →  Python
                ↑                                        |
                └──────────── Promise<T> ←───────────────┘
```

### 3.2 API 封装层

```typescript
// api/commands.ts — 前端唯一与后端交互的入口
import { invoke } from '@tauri-apps/api/core';

// ── 设备管理 ──
export const getDevices = () =>
  invoke<Device[]>('get_devices');

export const refreshDevices = () =>
  invoke<Device[]>('refresh_devices');

// ── 媒体解析 ──
export const parseMediaFile = (file_path: string) =>
  invoke<MediaInfo>('parse_media_file', { file_path });

export const parseMediaUrl = (url: string) =>
  invoke<MediaInfo>('parse_media_url', { url });

// ── 投屏控制 ──
export const startCast = (device_id: string, media_uri: string) =>
  invoke('start_cast', { device_id, media_uri });

export const stopCast = () =>
  invoke('stop_cast');

export const getCastState = () =>
  invoke<CastState>('get_cast_state');

export const setVolume = (volume: number) =>
  invoke('set_volume', { volume });

export const setMute = (muted: boolean) =>
  invoke('set_mute', { muted });

// ── 设置 ──
export const getSettings = () =>
  invoke<AppSettings>('get_settings');

export const saveSettings = (settings: AppSettings) =>
  invoke('save_settings', { settings });
```

### 3.3 事件监听 (后端主动推送)

```typescript
// api/events.ts — 监听 Python 通过 Rust 转发的事件
import { listen } from '@tauri-apps/api/event';

export function initEventListeners() {
  listen<CastState>('cast_state_changed', (event) => {
    // 更新投屏状态 store
    useCastStore().$patch(event.payload);
  });

  listen<Device>('device_found', (event) => {
    // 添加新设备到列表
    useDeviceStore().addDevice(event.payload);
  });

  listen<{ id: string }>('device_lost', (event) => {
    // 标记设备离线
    useDeviceStore().markOffline(event.payload.id);
  });

  listen<{ message: string }>('cast_error', (event) => {
    // 显示错误通知
    showError(event.payload.message);
  });
}
```

### 3.4 组件中的使用方式

```vue
<script setup lang="ts">
import { startCast, stopCast, getCastState } from '@/api/commands';
import { useDeviceStore } from '@/stores/device';
import { useCastStore } from '@/stores/cast';

const deviceStore = useDeviceStore();
const castStore = useCastStore();

// 点击投屏
async function handleCast(deviceId: string) {
  try {
    await startCast(deviceId, castStore.mediaUri);
    // 投屏成功，状态由事件推送更新
  } catch (error) {
    showError(error);  // "Device not found" 等
  }
}
</script>
```

---

## 4. 页面结构

### 3.1 整体布局

```
┌──────────────────────────────────────────┐
│              TitleBar (32px)              │  ← 自定义标题栏
├──────────────────────────────────────────┤
│                                          │
│          MediaInputSection               │  ← 拖拽区 + 链接输入
│              (flex-grow)                  │
│                                          │
├──────────────────────────────────────────┤
│          DeviceListSection               │  ← 局域网设备列表
│              (flex-grow)                  │
│                                          │
├──────────────────────────────────────────┤
│              Footer (24px)               │  ← 底部提示
└──────────────────────────────────────────┘
```

### 3.2 路由设计

| 路由 | 组件 | 说明 |
|------|------|------|
| `/` | `HomeView` | 主页面（投屏操作） |
| `/settings` | `SettingsView` | 设置面板 |
| `/device/:id` | `DeviceDetailView` | 设备详情（可选） |

---

## 5. 组件规格

### 4.1 TitleBar 标题栏

```
┌──────────────────────────────────────────┐
│  🖥️ HanCast              ⚙️    ─    ✕   │
└──────────────────────────────────────────┘
```

| 元素 | 类型 | 行为 |
|------|------|------|
| Logo + 标题 | `<span>` | 左对齐，可拖拽移动窗口 |
| 设置按钮 | `<button>` | 点击跳转 `/settings` |
| 最小化 | `<button>` | `appWindow.minimize()` |
| 关闭 | `<button>` | `appWindow.close()` |

**样式**:
```css
.title-bar {
  height: 32px;
  background: transparent;
  -webkit-app-region: drag;   /* 拖拽区域 */
  display: flex;
  align-items: center;
  padding: 0 8px;
}
.title-bar button {
  -webkit-app-region: no-drag; /* 按钮不触发拖拽 */
}
```

**Rust 壳层** — Tauri 命令:
```rust
#[tauri::command]
fn minimize_window(window: tauri::Window) { window.minimize().ok(); }

#[tauri::command]
fn close_window(window: tauri::Window) { window.close().ok(); }
```

---

### 4.2 MediaInputSection 媒体输入区

```
┌──────────────────────────────────────────┐
│              📁🎬🖼️🎵                    │
│         拖拽媒体文件到此处                │
│           或粘贴媒体链接                  │
│  ┌────────────────────────────────────┐  │
│  │ 🔗 支持视频/图片/音乐链接           │  │
│  │    [粘贴]  [解析/准备]              │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

**交互状态机**:
```
空闲态 → 拖拽悬停态 → 解析中态 → 就绪态
                ↘ 手动输入态 → 解析中态 → 就绪态
```

| 状态 | UI 表现 | 可用操作 |
|------|---------|----------|
| 空闲 | 虚线边框 | 拖拽文件、粘贴链接 |
| 拖拽悬停 | 蓝色高亮边框 | 释放文件 |
| 手动输入 | 输入框聚焦 | 输入 URL、粘贴 |
| 解析中 | Loading 动画 | 无 |
| 就绪 | 显示媒体预览信息 | 选择设备投屏 |

**前端 → Rust 命令**:
```typescript
// 文件拖拽：前端获取路径，Rust 处理
const mediaInfo = await invoke<MediaInfo>('parse_media_file', {
  file_path: '/path/to/file.mp4'
});

// 链接解析
const mediaInfo = await invoke<MediaInfo>('parse_media_url', {
  url: 'https://example.com/video.mp4'
});
```

**支持格式** (前端仅做文件扩展名过滤):
| 类型 | 扩展名 |
|------|--------|
| 视频 | `.mp4 .mkv .avi .mov .webm .flv` |
| 音频 | `.mp3 .flac .wav .aac .ogg .m4a` |
| 图片 | `.jpg .jpeg .png .gif .bmp .webp` |

---

### 4.3 DeviceListSection 设备列表区

```
┌──────────────────────────────────────────┐
│  🖥️ 局域网设备                      🔄  │
├──────────────────────────────────────────┤
│  🟢 🖥️ Samsung TV    [默认]  [投屏] [⋮] │
│  🟢 🔊 [客厅音箱] (音箱) ☑同步 [投屏] [⋮]│
│  ⚪ 📦 小米盒子     离线    不适用   [⋮] │
└──────────────────────────────────────────┘
```

**设备卡片状态**:
| 状态 | 指示灯 | 投屏按钮 |
|------|--------|----------|
| Online | 🟢 绿色 | 可点击 |
| Busy | 🟡 黄色 | 禁用 |
| Offline | ⚪ 灰色 | 隐藏，显示"不适用" |

**前端状态管理 (Pinia Store)**:
```typescript
// stores/device.ts
export const useDeviceStore = defineStore('device', () => {
  const devices = ref<Device[]>([]);
  const selectedDevice = ref<Device | null>(null);

  async function refreshDevices() {
    devices.value = await invoke<Device[]>('get_devices');
  }

  async function startCast(device_id: string, media_uri: string) {
    await invoke('start_cast', { device_id, media_uri });
  }

  // 自动刷新：每 30 秒
  let timer: number;
  onMounted(() => {
    refreshDevices();
    timer = window.setInterval(refreshDevices, 30000);
  });
  onUnmounted(() => clearInterval(timer));

  return { devices, selectedDevice, refreshDevices, startCast };
});
```

**更多菜单**:
| 选项 | Rust 命令 |
|------|-----------|
| 设为默认设备 | `set_default_device` |
| 重命名 | `rename_device` |
| 移除设备 | `remove_device` |
| 设备信息 | `get_device_info` |

---

### 4.4 Footer 底部提示

```
┌──────────────────────────────────────────┐
│ ℹ️ 未检测到设备？请确保设备与此电脑连接同一 Wi-Fi │
└──────────────────────────────────────────┘
```

- 仅在设备列表为空时显示
- 点击可展开网络诊断提示

---

### 4.5 SettingsPanel 设置面板

| 分组 | 设置项 | 组件 | Rust 命令 |
|------|--------|------|-----------|
| **通用** | 开机自启 | `<Toggle>` | `set_auto_start` |
| | 语言 | `<Select>` | `set_language` |
| | 通知 | `<Toggle>` | `set_notification` |
| **投屏** | DLNA 名称 | `<Input>` | `set_dlna_name` |
| | 默认端口 | `<Input>` | `set_port` |
| | 自动接受 | `<Toggle>` | `set_auto_accept` |
| **网络** | 网络接口 | `<MultiSelect>` | `set_interfaces` |
| | 代理 | `<Input>` | `set_proxy` |
| **关于** | 版本 | `<Text>` | `get_version` |
| | 检查更新 | `<Button>` | `check_update` |
| | 开源许可 | `<Link>` | — |

---

## 6. 数据类型定义 (TypeScript)

```typescript
// types/device.ts
export interface Device {
  id: string;
  name: string;
  type: 'tv' | 'speaker' | 'box' | 'unknown';
  ip: string;
  port: number;
  status: 'online' | 'busy' | 'offline';
  isDefault: boolean;
  multiRoomSync: boolean;
  manufacturer?: string;
  modelName?: string;
  udn: string;
}

// types/media.ts
export interface MediaInfo {
  type: 'file' | 'url';
  uri: string;
  title: string;
  duration?: number;        // 秒
  mimeType: string;
  fileSize?: number;        // 字节
  thumbnail?: string;
}

// types/cast.ts
export interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'error';
  deviceId?: string;
  media?: MediaInfo;
  position?: number;        // 秒
  volume?: number;          // 0-100
  isMuted?: boolean;
}

// types/settings.ts
// 注：此结构直接映射 Python Config 类的 to_dict() 返回值
export interface AppSettings {
  usn: string;                    // 设备唯一标识
  friendly_name: string;          // 设备友好名称 (DLNA 广播名)
  version: string;                // 版本号
  media_port: number;             // 媒体服务端口
  default_device: string | null;  // 默认设备 ID
  settings: Record<string, any>;  // 其他设置 (语言/通知/代理等)
}
```

---

## 7. Tauri 命令清单 (前端可调用)

```typescript
// api/commands.ts
import { invoke } from '@tauri-apps/api/core';

// ── 设备管理 ──
export const getDevices = () => invoke<Device[]>('get_devices');
export const refreshDevices = () => invoke<Device[]>('refresh_devices');
export const setDefaultDevice = (id: string) => invoke('set_default_device', { id });
export const renameDevice = (id: string, name: string) => invoke('rename_device', { id, name });
export const removeDevice = (id: string) => invoke('remove_device', { id });

// ── 媒体解析 ──
export const parseMediaFile = (file_path: string) => invoke<MediaInfo>('parse_media_file', { file_path });
export const parseMediaUrl = (url: string) => invoke<MediaInfo>('parse_media_url', { url });

// ── 投屏控制 ──
export const startCast = (device_id: string, media_uri: string) => invoke('start_cast', { device_id, media_uri });
export const stopCast = () => invoke('stop_cast');
export const pauseCast = () => invoke('pause_cast');
export const resumeCast = () => invoke('resume_cast');
export const seekCast = (position: string) => invoke('seek_cast', { position });
export const getCastState = () => invoke<CastState>('get_cast_state');
export const setVolume = (volume: number) => invoke('set_volume', { volume });
export const setMute = (muted: boolean) => invoke('set_mute', { muted });

// ── 设置 ──
export const getSettings = () => invoke<AppSettings>('get_settings');
export const saveSettings = (settings: AppSettings) => invoke('save_settings', { settings });
```

---

## 8. 样式系统

### 7.1 CSS 变量

```css
:root {
  /* 主色 */
  --primary: #3B82F6;
  --primary-hover: #2563EB;
  --primary-active: #1D4ED8;

  /* 背景 (配合系统特效) */
  --bg-primary: rgba(255, 255, 255, 0.85);
  --bg-secondary: rgba(243, 244, 246, 0.9);
  --bg-card: rgba(255, 255, 255, 0.95);

  /* 文字 */
  --text-primary: #111827;
  --text-secondary: #6B7280;
  --text-tertiary: #9CA3AF;

  /* 状态 */
  --status-online: #10B981;
  --status-busy: #F59E0B;
  --status-offline: #9CA3AF;

  /* 边框 */
  --border: #E5E7EB;
  --border-focus: #3B82F6;

  /* 间距 */
  --sp-xs: 4px; --sp-sm: 8px; --sp-md: 12px;
  --sp-lg: 16px; --sp-xl: 24px; --sp-2xl: 32px;

  /* 圆角 */
  --r-sm: 4px; --r-md: 8px; --r-lg: 12px; --r-full: 9999px;

  /* 字体 */
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI',
          'PingFang SC', 'Microsoft YaHei', sans-serif;
}
```

### 7.2 暗色主题

```css
[data-theme="dark"] {
  --bg-primary: rgba(17, 24, 39, 0.85);
  --bg-secondary: rgba(31, 41, 55, 0.9);
  --bg-card: rgba(31, 41, 55, 0.95);
  --text-primary: #F9FAFB;
  --text-secondary: #D1D5DB;
  --text-tertiary: #6B7280;
  --border: #374151;
}
```

### 7.3 响应式断点

| 断点 | 宽度 | 布局调整 |
|------|------|----------|
| `< 360px` | 不支持 | 显示提示 |
| `360-480px` | 紧凑 | 单列，缩小间距 |
| `480-768px` | 默认 | 标准布局 |
| `> 768px` | 宽松 | 可选双列设备列表 |

---

## 9. 国际化

```jsonc
// locales/zh-CN.json
{
  "app.title": "HanCast",
  "media.dragHint": "拖拽媒体文件到此处",
  "media.pasteHint": "或粘贴媒体链接",
  "media.linkPlaceholder": "支持视频 / 图片 / 音乐链接",
  "media.paste": "粘贴",
  "media.parse": "解析 / 准备",
  "media.ready": "就绪，等待投屏",
  "devices.title": "局域网设备",
  "devices.refresh": "刷新",
  "devices.cast": "投屏",
  "devices.setDefault": "设为默认设备",
  "devices.rename": "重命名",
  "devices.remove": "移除设备",
  "devices.offline": "离线",
  "devices.notApplicable": "不适用",
  "footer.noDevice": "未检测到设备？请确保设备与此电脑连接同一 Wi-Fi 网络",
  "settings.title": "设置",
  "settings.general": "通用",
  "settings.cast": "投屏",
  "settings.network": "网络",
  "settings.about": "关于"
}
```

---

## 10. 前端项目结构

```
src/
├── main.ts                   # 入口
├── App.vue                   # 根组件
├── router/
│   └── index.ts              # Vue Router
├── stores/
│   ├── device.ts             # 设备状态
│   ├── media.ts              # 媒体状态
│   ├── cast.ts               # 投屏状态
│   └── settings.ts           # 设置状态
├── views/
│   ├── HomeView.vue          # 主页面
│   └── SettingsView.vue      # 设置页面
├── components/
│   ├── TitleBar.vue           # 自定义标题栏
│   ├── MediaInput.vue         # 媒体输入区
│   ├── DeviceList.vue         # 设备列表
│   ├── DeviceCard.vue         # 设备卡片
│   ├── CastControl.vue        # 投屏控制
│   └── Footer.vue             # 底部提示
├── api/
│   └── commands.ts            # Tauri invoke 封装
├── types/
│   ├── device.ts
│   ├── media.ts
│   ├── cast.ts
│   └── settings.ts
├── locales/
│   ├── zh-CN.json
│   └── en-US.json
└── styles/
    ├── variables.css           # CSS 变量
    └── global.css              # 全局样式
```

---

## 11. 前端开发任务

### Phase 1: 项目初始化
- [ ] `npm create tauri-app hancast -- --template vue-ts`
- [ ] 配置 Vite + Vue 3 + TypeScript
- [ ] 集成 Pinia、vue-i18n、vue-router
- [ ] 配置 tauri-plugin-vibrancy / tauri-plugin-mica

### Phase 2: 基础 UI
- [ ] 实现 TitleBar（自定义标题栏 + 窗口控制）
- [ ] 实现 CSS 变量系统 + 暗色主题
- [ ] 实现响应式布局骨架

### Phase 3: 核心组件
- [ ] 实现 MediaInput（拖拽 + 链接输入 + 状态机）
- [ ] 实现 DeviceList + DeviceCard
- [ ] 实现 CastControl
- [ ] 实现 SettingsView

### Phase 4: 状态与通信
- [ ] 实现 Pinia stores（device/media/cast/settings）
- [ ] 封装 Tauri invoke 命令层
- [ ] 实现事件监听（Rust → 前端推送）

### Phase 5: 国际化与打磨
- [ ] 集成 vue-i18n，添加中英文
- [ ] 动画与过渡效果
- [ ] 错误处理与边界状态
- [ ] 跨平台 WebView 测试
