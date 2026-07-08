# HanCast 2.0 — 前端 API 接口文档

> **目标读者**: 前端开发者
> **技术栈**: Tauri 2.0 + Vue 3 + TypeScript
> **最后更新**: 2026-07-06

---

## 1. 系统架构

HanCast 2.0 是三层架构应用：

```
┌─────────────────────────────────────────────┐
│  第一层: 前端 (Vue 3 + Vite)                 │
│  - UI 渲染、用户交互                          │
│  - 通过 Tauri IPC 调用 Rust 后端              │
├─────────────────────────────────────────────┤
│  第二层: Rust 桥接 (Tauri Core)               │
│  - 窗口管理、系统托盘                          │
│  - 管理 Python Sidecar 进程                   │
│  - stdin/stdout JSON 协议通信                 │
├─────────────────────────────────────────────┤
│  第三层: Python 后端 (Sidecar)                │
│  - SSDP 设备发现 (端口 1900)                  │
│  - DLNA 协议处理 (端口 8080)                  │
│  - MPV 播放器控制 (IPC)                       │
│  - 媒体文件 HTTP 服务 (随机端口)               │
└─────────────────────────────────────────────┘
```

### 通信协议

Rust ↔ Python 通过 stdin/stdout 使用 JSON 行协议：

```json
// 请求 (Rust → Python)
{"id": 1, "cmd": "get_devices", "params": {}}

// 响应 (Python → Rust)
{"id": 1, "success": true, "data": [...]}

// 事件推送 (Python → Rust)
{"event": "device_found", "data": {"id": "...", "name": "..."}}
```

---

## 2. 启动方法

### 2.1 完整应用启动（推荐）

一键启动前端 + Rust + Python 全部三层：

```bash
# 安装前端依赖（首次）
npm install

# 安装 Python 依赖（首次）
cd hancast-backend && uv sync && cd ..

# 启动完整应用
npx tauri dev
```

`tauri dev` 会自动：
1. 启动 Vite 开发服务器（`localhost:1420`）
2. 编译并启动 Rust 应用
3. Rust 自动拉起 Python Sidecar 进程

### 2.2 单独启动各层（开发调试）

#### 前端开发服务器

```bash
npm run dev
# → Vite 启动在 http://localhost:1420
# 仅用于前端 UI 开发，不包含 Rust 和 Python
```

#### Rust 应用

```bash
cd src-tauri
cargo build          # 编译
cargo run            # 运行（会自动拉起 Python sidecar）
```

#### Python Sidecar（独立测试）

```bash
cd hancast-backend

# 方式 1: 持续运行模式（带界面输出）
uv run python scripts/run_sidecar.py

# 方式 2: stdin/stdout 模式（供 Rust 调用）
uv run python -m hancast_sidecar.main
```

独立运行 Sidecar 可用于：
- 测试 DLNA 投屏功能（无需启动 Tauri）
- 调试 SSDP 设备发现
- 验证 MPV 播放器连接

### 2.3 生产构建

```bash
npx tauri build
# → 输出安装包到 src-tauri/target/release/bundle/
```

### 2.4 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Node.js | >= 18 | 前端构建 |
| Rust | >= 1.75 | Tauri 编译 |
| Python | >= 3.11 | 后端运行 |
| uv | >= 0.5 | Python 包管理 |
| MPV | 最新版 | 媒体播放器 |

---

## 3. API 接口列表

### 3.1 设备管理

#### `get_devices()`

获取所有已发现的 DLNA 设备列表。

```typescript
const devices: Device[] = await invoke('get_devices');
```

**返回值**: `Device[]`

```typescript
interface Device {
  id: string;           // 设备唯一标识 (UDN)
  name: string;         // 设备名称
  type: 'tv' | 'speaker' | 'box' | 'unknown';  // 设备类型
  ip: string;           // 设备 IP 地址
  port: number;         // 设备端口
  status: 'online' | 'busy' | 'offline';  // 设备状态
  is_default: boolean;  // 是否为默认设备
  manufacturer?: string;  // 制造商
  model_name?: string;   // 型号
  udn: string;          // 唯一设备名称
}
```

**示例**:
```typescript
const devices = await invoke('get_devices');
devices.forEach(device => {
  console.log(`${device.name} (${device.ip})`);
});
```

---

#### `refresh_devices()`

触发设备扫描，返回最新设备列表。

```typescript
const devices: Device[] = await invoke('refresh_devices');
```

**返回值**: `Device[]` (同 `get_devices`)

**说明**: 调用后会触发 SSDP 扫描，新发现的设备会通过 `device_found` 事件推送。

---

#### `set_default_device(device_id: string)`

设置默认设备。

```typescript
await invoke('set_default_device', { id: device_id });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 ID |

**返回值**: `null`

---

#### `rename_device(device_id: string, name: string)`

重命名设备。

```typescript
await invoke('rename_device', { id: device_id, name: '客厅电视' });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 ID |
| `name` | `string` | 新名称 |

**返回值**: `null`

---

#### `remove_device(device_id: string)`

移除设备（从当前列表移除，下次扫描可能重新出现）。

```typescript
await invoke('remove_device', { id: device_id });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 ID |

**返回值**: `null`

---

#### `hide_device(device_id: string)`

隐藏设备（加入隐藏列表，后续扫描不再显示）。

```typescript
await invoke('hide_device', { id: device_id });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 UDN |

**返回值**: `null`

**说明**: 隐藏的设备会持久化存储，应用重启后仍然生效。与 `remove_device` 不同，`hide_device` 会阻止设备在后续 SSDP 扫描中被重新发现。

---

#### `unhide_device(device_id: string)`

取消隐藏设备（从隐藏列表移除）。

```typescript
await invoke('unhide_device', { id: device_id });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 UDN |

**返回值**: `null`

---

#### `get_hidden_devices()`

获取当前隐藏的设备 UDN 列表。

```typescript
const hiddenDevices: string[] = await invoke('get_hidden_devices');
```

**参数**: 无

**返回值**: `string[]` — 隐藏设备的 UDN 列表

**示例**:
```typescript
const hidden = await invoke('get_hidden_devices');
console.log(`当前隐藏了 ${hidden.length} 个设备`);
```

---

### 3.2 投屏控制

#### `start_cast(device_id: string, media_uri: string)`

开始投屏到指定设备。

```typescript
await invoke('start_cast', {
  device_id: device_id,
  media_uri: media_uri
});
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `device_id` | `string` | 目标设备 ID |
| `media_uri` | `string` | 媒体 URI (本地文件路径或 HTTP URL) |

**返回值**: `null`

**示例**:
```typescript
// 投屏本地文件
await invoke('start_cast', {
  device_id: 'uuid-xxxx',
  media_uri: 'C:\\Videos\\movie.mp4'
});

// 投屏网络链接
await invoke('start_cast', {
  device_id: 'uuid-xxxx',
  media_uri: 'http://example.com/video.mp4'
});
```

---

#### `stop_cast()`

停止当前投屏。

```typescript
await invoke('stop_cast');
```

**参数**: 无

**返回值**: `null`

---

#### `pause_cast()`

暂停当前投屏。

```typescript
await invoke('pause_cast');
```

**参数**: 无

**返回值**: `null`

---

#### `resume_cast()`

恢复当前投屏。

```typescript
await invoke('resume_cast');
```

**参数**: 无

**返回值**: `null`

---

#### `seek_cast(position: string)`

跳转到指定位置。

```typescript
await invoke('seek_cast', { position: '00:05:30' });
```

**参数**:
| 参数 | 类型 | 格式 | 说明 |
|------|------|------|------|
| `position` | `string` | `HH:MM:SS` | 目标位置 |

**返回值**: `null`

---

#### `get_cast_state()`

获取当前投屏状态。

```typescript
const state: CastState = await invoke('get_cast_state');
```

**返回值**: `CastState`

```typescript
interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'error';  // 投屏状态
  device_id: string | null;  // 当前投屏设备 ID
  media: MediaInfo | null;   // 当前媒体信息
  position: number;          // 当前播放位置 (秒)
  volume: number;            // 音量 (0-100)
  is_muted: boolean;         // 是否静音
}

interface MediaInfo {
  type: 'file' | 'url';     // 媒体类型
  uri: string;               // 媒体 URI
  title: string;             // 媒体标题
  duration: number | null;   // 时长 (秒)
  mime_type: string;         // MIME 类型
  file_size: number | null;  // 文件大小 (字节)
  thumbnail: string | null;  // 缩略图 URL
}
```

---

#### `get_cast_url()`

获取当前投屏元素的 URL 和播放进度信息。适用于前端需要显示当前投屏内容、进度条等场景。

```typescript
const info: CastUrlInfo = await invoke('get_cast_url');
```

**返回值**: `CastUrlInfo`

```typescript
interface CastUrlInfo {
  url: string;       // 当前投屏媒体 URL（为空表示无投屏）
  title: string;     // 媒体标题
  duration: string;  // 总时长，格式 HH:MM:SS
  position: string;  // 当前进度，格式 HH:MM:SS
  status: string;    // 播放状态: PLAYING / PAUSED_PLAYBACK / STOPPED / NO_MEDIA_PRESENT
}
```

**示例**:
```typescript
const info = await invoke('get_cast_url');
if (info.url) {
  console.log(`正在投屏: ${info.title}`);
  console.log(`进度: ${info.position} / ${info.duration}`);
  console.log(`URL: ${info.url}`);
} else {
  console.log('当前无投屏');
}
```

**说明**:
- 当无投屏时，`url` 为空字符串，`status` 为 `STOPPED`
- `duration` 和 `position` 格式为 `HH:MM:SS` 或 `H:MM:SS`
- 此接口轻量，适合轮询（如每秒调用一次更新进度条）

---

#### `set_volume(volume: number)`

设置音量。

```typescript
await invoke('set_volume', { volume: 80 });
```

**参数**:
| 参数 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `volume` | `number` | 0-100 | 音量值 |

**返回值**: `null`

---

#### `set_mute(muted: boolean)`

设置静音。

```typescript
await invoke('set_mute', { muted: true });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `muted` | `boolean` | 是否静音 |

**返回值**: `null`

---

### 3.3 媒体解析

#### `parse_media_file(filePath: string)`

解析本地媒体文件。

```typescript
const mediaInfo: MediaInfo = await invoke('parse_media_file', {
  file_path: 'C:\\Videos\\movie.mp4'
});
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `file_path` | `string` | 本地文件路径 |

**返回值**: `MediaInfo`

---

#### `parse_media_url(url: string)`

解析网络媒体链接。

```typescript
const mediaInfo: MediaInfo = await invoke('parse_media_url', {
  url: 'http://example.com/video.mp4'
});
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `url` | `string` | 媒体 URL |

**返回值**: `MediaInfo`

---

### 3.4 设置管理

#### `get_settings()`

获取应用设置。

```typescript
const settings: AppSettings = await invoke('get_settings');
```

**返回值**: `AppSettings`

```typescript
interface AppSettings {
  usn: string;              // 设备唯一标识
  friendly_name: string;    // 设备友好名称
  version: string;          // 版本号
  media_port: number;       // 媒体服务端口
  default_device: string | null;  // 默认设备 ID
  settings: Record<string, any>;  // 其他设置
}
```

---

#### `save_settings(settings: Partial<AppSettings>)`

保存应用设置。

```typescript
await invoke('save_settings', {
  settings: {
    friendly_name: '我的 HanCast',
    default_device: 'uuid-xxxx'
  }
});
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `settings` | `Partial<AppSettings>` | 要更新的设置项 |

**返回值**: `null`

---

## 4. 事件监听

### 4.1 事件列表

| 事件名 | 触发时机 | Payload 类型 |
|--------|----------|--------------|
| `device_found` | 发现新设备 | `Device` |
| `device_lost` | 设备离线 | `{ id: string }` |
| `cast_state_changed` | 投屏状态变化 | `CastState` |
| `cast_error` | 投屏出错 | `{ message: string }` |

### 4.2 监听示例

```typescript
import { listen } from '@tauri-apps/api/event';

// 监听设备发现
const unlistenDevice = await listen<Device>('device_found', (event) => {
  const device = event.payload;
  console.log(`发现新设备: ${device.name} (${device.ip})`);
  // 更新设备列表
  devices.value.push(device);
});

// 监听设备离线
const unlistenDeviceLost = await listen<{ id: string }>('device_lost', (event) => {
  const { id } = event.payload;
  console.log(`设备离线: ${id}`);
  // 从列表中移除
  devices.value = devices.value.filter(d => d.id !== id);
});

// 监听投屏状态变化
const unlistenCastState = await listen<CastState>('cast_state_changed', (event) => {
  const state = event.payload;
  console.log(`投屏状态: ${state.status}`);
  // 更新 UI
  castState.value = state;
});

// 监听投屏错误
const unlistenCastError = await listen<{ message: string }>('cast_error', (event) => {
  const { message } = event.payload;
  console.error(`投屏错误: ${message}`);
  // 显示错误提示
  showToast(message, 'error');
});

// 组件卸载时取消监听
onUnmounted(() => {
  unlistenDevice();
  unlistenDeviceLost();
  unlistenCastState();
  unlistenCastError();
});
```

---

## 5. 错误处理

### 5.1 错误类型

所有 API 调用都可能抛出错误，错误信息为字符串。

```typescript
try {
  await invoke('start_cast', {
    device_id: deviceId,
    media_uri: mediaUri
  });
} catch (error) {
  // error 是字符串类型的错误信息
  console.error('投屏失败:', error);
}
```

### 5.2 常见错误

| 错误信息 | 原因 | 处理建议 |
|----------|------|----------|
| `Device not found` | 设备 ID 不存在 | 刷新设备列表 |
| `File not found` | 本地文件不存在 | 提示用户检查文件路径 |
| `URL not reachable` | 网络链接不可达 | 提示用户检查网络 |
| `Unsupported format` | 不支持的媒体格式 | 提示用户选择支持的格式 |
| `Unknown command` | 命令不存在 | 检查命令拼写 |

### 5.3 错误处理示例

```typescript
import { message } from '@tauri-apps/plugin-dialog';

async function handleCast(deviceId: string, mediaUri: string) {
  try {
    await invoke('start_cast', {
      device_id: deviceId,
      media_uri: mediaUri
    });
    await message('投屏成功', { title: 'HanCast', type: 'info' });
  } catch (error) {
    await message(`投屏失败: ${error}`, { title: 'HanCast', type: 'error' });
  }
}
```

---

## 6. 完整示例

### 6.1 设备列表组件

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';

interface Device {
  id: string;
  name: string;
  type: 'tv' | 'speaker' | 'box' | 'unknown';
  ip: string;
  port: number;
  status: 'online' | 'busy' | 'offline';
  is_default: boolean;
}

const devices = ref<Device[]>([]);
const loading = ref(false);
const unlistenFns: UnlistenFn[] = [];

onMounted(async () => {
  // 获取设备列表
  loading.value = true;
  try {
    devices.value = await invoke('get_devices');
  } catch (error) {
    console.error('获取设备失败:', error);
  } finally {
    loading.value = false;
  }

  // 监听设备发现
  unlistenFns.push(
    await listen<Device>('device_found', (event) => {
      const device = event.payload;
      if (!devices.value.find(d => d.id === device.id)) {
        devices.value.push(device);
      }
    })
  );

  // 监听设备离线
  unlistenFns.push(
    await listen<{ id: string }>('device_lost', (event) => {
      devices.value = devices.value.filter(d => d.id !== event.payload.id);
    })
  );
});

onUnmounted(() => {
  unlistenFns.forEach(fn => fn());
});

async function refreshDevices() {
  loading.value = true;
  try {
    devices.value = await invoke('refresh_devices');
  } catch (error) {
    console.error('刷新设备失败:', error);
  } finally {
    loading.value = false;
  }
}

async function selectDevice(device_id: string) {
  try {
    await invoke('set_default_device', { id: device_id });
    devices.value = devices.value.map(d => ({
      ...d,
      is_default: d.id === device_id
    }));
  } catch (error) {
    console.error('设置默认设备失败:', error);
  }
}
</script>

<template>
  <div class="device-list">
    <div class="header">
      <h2>设备列表</h2>
      <button @click="refreshDevices" :disabled="loading">
        {{ loading ? '扫描中...' : '刷新' }}
      </button>
    </div>
    <div v-if="devices.length === 0" class="empty">
      未发现设备，请点击刷新
    </div>
    <div v-else class="devices">
      <div
        v-for="device in devices"
        :key="device.id"
        :class="['device', { active: device.is_default }]"
        @click="selectDevice(device.id)"
      >
        <span class="icon">{{ device.type === 'tv' ? '📺' : '🔊' }}</span>
        <span class="name">{{ device.name }}</span>
        <span class="status" :class="device.status">
          {{ device.status === 'online' ? '在线' : '离线' }}
        </span>
      </div>
    </div>
  </div>
</template>
```

### 6.2 投屏控制组件

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';

interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'error';
  device_id: string | null;
  position: number;
  volume: number;
  is_muted: boolean;
}

const props = defineProps<{
  deviceId: string;
  mediaUri: string;
}>();

const castState = ref<CastState | null>(null);
const unlistenFns: UnlistenFn[] = [];

onMounted(async () => {
  // 获取初始状态
  castState.value = await invoke('get_cast_state');

  // 监听状态变化
  unlistenFns.push(
    await listen<CastState>('cast_state_changed', (event) => {
      castState.value = event.payload;
    })
  );

  // 监听错误
  unlistenFns.push(
    await listen<{ message: string }>('cast_error', (event) => {
      alert(`投屏错误: ${event.payload.message}`);
    })
  );
});

onUnmounted(() => {
  unlistenFns.forEach(fn => fn());
});

async function startCast() {
  try {
    await invoke('start_cast', {
      device_id: props.deviceId,
      media_uri: props.mediaUri
    });
  } catch (error) {
    alert(`投屏失败: ${error}`);
  }
}

async function stopCast() {
  try {
    await invoke('stop_cast');
  } catch (error) {
    alert(`停止失败: ${error}`);
  }
}

async function togglePause() {
  try {
    if (castState.value?.status === 'playing') {
      await invoke('pause_cast');
    } else {
      await invoke('resume_cast');
    }
  } catch (error) {
    alert(`操作失败: ${error}`);
  }
}

async function setVolume(volume: number) {
  try {
    await invoke('set_volume', { volume });
  } catch (error) {
    alert(`设置音量失败: ${error}`);
  }
}

async function toggleMute() {
  try {
    await invoke('set_mute', { muted: !castState.value?.is_muted });
  } catch (error) {
    alert(`设置静音失败: ${error}`);
  }
}

async function seek(position: string) {
  try {
    await invoke('seek_cast', { position });
  } catch (error) {
    alert(`跳转失败: ${error}`);
  }
}
</script>

<template>
  <div class="cast-control">
    <div v-if="castState?.status === 'idle'" class="idle">
      <button @click="startCast">开始投屏</button>
    </div>
    <div v-else class="playing">
      <div class="status">
        状态: {{ castState?.status === 'playing' ? '播放中' : '已暂停' }}
      </div>
      <div class="controls">
        <button @click="togglePause">
          {{ castState?.status === 'playing' ? '暂停' : '播放' }}
        </button>
        <button @click="stopCast">停止</button>
        <button @click="toggleMute">
          {{ castState?.is_muted ? '取消静音' : '静音' }}
        </button>
      </div>
      <div class="volume">
        <input
          type="range"
          min="0"
          max="100"
          :value="castState?.volume"
          @input="setVolume(Number($event.target.value))"
        />
        <span>{{ castState?.volume }}%</span>
      </div>
    </div>
  </div>
</template>
```

---

## 7. TypeScript 类型定义

将以下内容保存为 `types/api.ts`:

```typescript
// 设备类型
export interface Device {
  id: string;
  name: string;
  type: 'tv' | 'speaker' | 'box' | 'unknown';
  ip: string;
  port: number;
  status: 'online' | 'busy' | 'offline';
  is_default: boolean;
  manufacturer?: string;
  model_name?: string;
  udn: string;
}

// 媒体信息
export interface MediaInfo {
  type: 'file' | 'url';
  uri: string;
  title: string;
  duration: number | null;
  mime_type: string;
  file_size: number | null;
  thumbnail: string | null;
}

// 投屏状态
export interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'error';
  device_id: string | null;
  media: MediaInfo | null;
  position: number;
  volume: number;
  is_muted: boolean;
}

// 投屏 URL 信息
export interface CastUrlInfo {
  url: string;       // 当前投屏媒体 URL
  title: string;     // 媒体标题
  duration: string;  // 总时长 HH:MM:SS
  position: string;  // 当前进度 HH:MM:SS
  status: string;    // 播放状态
}

// 应用设置
export interface AppSettings {
  usn: string;
  friendly_name: string;
  version: string;
  media_port: number;
  default_device: string | null;
  settings: Record<string, any>;
}

// 事件类型
export interface DeviceLostEvent {
  id: string;
}

export interface CastErrorEvent {
  message: string;
}
```

---

## 8. API 快速参考表

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_devices()` | - | `Device[]` | 获取设备列表 |
| `refresh_devices()` | - | `Device[]` | 触发扫描 |
| `set_default_device(device_id)` | `{ id: string }` | `null` | 设置默认设备 |
| `rename_device(device_id, name)` | `{ id, name }` | `null` | 重命名设备 |
| `remove_device(device_id)` | `{ id: string }` | `null` | 移除设备 |
| `hide_device(device_id)` | `{ id: string }` | `null` | 隐藏设备 |
| `unhide_device(device_id)` | `{ id: string }` | `null` | 取消隐藏 |
| `get_hidden_devices()` | - | `string[]` | 获取隐藏列表 |
| `start_cast(device_id, media_uri)` | `{ device_id, media_uri }` | `null` | 开始投屏 |
| `stop_cast()` | - | `null` | 停止投屏 |
| `pause_cast()` | - | `null` | 暂停投屏 |
| `resume_cast()` | - | `null` | 恢复投屏 |
| `seek_cast(position)` | `{ position: string }` | `null` | 跳转位置 |
| `get_cast_state()` | - | `CastState` | 获取状态 |
| `get_cast_url()` | - | `CastUrlInfo` | 获取投屏URL和进度 |
| `set_volume(volume)` | `{ volume: number }` | `null` | 设置音量 |
| `set_mute(muted)` | `{ muted: boolean }` | `null` | 设置静音 |
| `parse_media_file(path)` | `{ file_path: string }` | `MediaInfo` | 解析文件 |
| `parse_media_url(url)` | `{ url: string }` | `MediaInfo` | 解析链接 |
| `get_settings()` | - | `AppSettings` | 获取设置 |
| `save_settings(settings)` | `{ settings }` | `null` | 保存设置 |
| `respond_cast_confirm(requestId, approved, policy)` | `{ request_id, approved, policy }` | `boolean` | 响应投屏确认 |
| `get_guard_devices()` | - | `{ trusted, blacklisted }` | 获取确认设备列表 |
| `remove_guard_device(deviceKey)` | `{ device_key }` | `boolean` | 移除确认设备 |
| `set_guard_policy(deviceKey, policy)` | `{ device_key, policy }` | `boolean` | 修改设备策略 |
| `get_guard_settings()` | - | `GuardSettings` | 获取确认设置 |
| `save_guard_settings(settings)` | `{ enabled?, confirm_timeout? }` | `null` | 保存确认设置 |

| 事件 | Payload | 说明 |
|------|---------|------|
| `device_found` | `Device` | 发现新设备 |
| `device_lost` | `{ id }` | 设备离线 |
| `cast_state_changed` | `CastState` | 状态变化 |
| `cast_error` | `{ message }` | 投屏错误 |
| `cast_confirm_request` | `CastConfirmRequest` | 入站投屏确认请求 |

---

## 9. Device Guard（投屏设备确认）

### 9.1 工作原理

当外部设备尝试投屏到本机（DLNA Renderer）时，系统根据设备信任状态决定行为：

| 状态 | 行为 |
|------|------|
| **trusted** | 直接放行 |
| **blacklisted** | 直接拒绝（返回 SOAP Fault） |
| **未知** | 发送 `cast_confirm_request` 事件，阻塞等待用户确认（15s 超时默认拒绝） |

设备标识优先使用 UDN（通过 HTTP 反查 description.xml 获取），回退使用 IP。

### 9.2 确认流程

```
1. 外部设备发送 SetAVTransportURI → Python 后端
2. DeviceGuard.check() 判断设备状态
3. 若未知 → emit "cast_confirm_request" 事件到前端
4. Python HTTP 线程阻塞等待（15s 超时）
5. 前端弹窗 → 用户选择 → 调用 respond_cast_confirm()
6. Python 收到响应 → 放行或拒绝
7. 若超时 → 自动拒绝
```

### 9.3 命令

```typescript
// 响应投屏确认
invoke("respond_cast_confirm", {
  requestId: string,    // 确认请求 ID
  approved: boolean,    // 是否允许
  policy: string        // "once" | "always" | "blacklist"
})

// 获取设备列表（信任 + 黑名单）
invoke("get_guard_devices")
// 返回: { trusted: GuardEntry[], blacklisted: GuardEntry[] }

// 移除设备（从信任/黑名单中删除）
invoke("remove_guard_device", { deviceKey: string })
// deviceKey: UDN 或 IP

// 修改设备策略
invoke("set_guard_policy", {
  deviceKey: string,    // UDN 或 IP
  policy: string        // "trusted" | "blacklisted"
})

// 获取确认设置
invoke("get_guard_settings")
// 返回: { enabled: boolean, confirm_timeout: number }

// 保存确认设置
invoke("save_guard_settings", {
  enabled?: boolean,
  confirm_timeout?: number
})
```

### 9.4 事件

```typescript
// 监听投屏确认请求
listen("cast_confirm_request", (event) => {
  const { request_id, device, timeout } = event.payload;
  // device: { ip, udn, friendly_name, model_name }
  // timeout: 等待秒数
})

// 类型定义
interface CastConfirmRequest {
  request_id: string;
  device: {
    ip: string;
    udn: string;
    friendly_name: string;
    model_name: string;
  };
  timeout: number;
}

interface GuardEntry {
  udn: string;
  ip: string;
  friendly_name: string;
  policy: "trusted" | "blacklisted";
  created_at: string;      // ISO 时间戳
  last_seen_at: string;
  cast_count: number;
}
```
