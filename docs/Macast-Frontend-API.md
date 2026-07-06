# Macast 2.0 — 前端 API 接口文档

> **目标读者**: 前端开发者
> **技术栈**: Tauri 2.0 + Vue 3 + TypeScript
> **最后更新**: 2026-07-05

---

## 1. 快速开始

### 1.1 安装依赖

```bash
npm install @tauri-apps/api
```

### 1.2 基础用法

```typescript
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

// 调用后端命令
const devices = await invoke('get_devices');

// 监听事件
const unlisten = await listen('device_found', (event) => {
  console.log('发现新设备:', event.payload);
});
```

---

## 2. API 接口列表

### 2.1 设备管理

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

移除设备。

```typescript
await invoke('remove_device', { id: device_id });
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 设备 ID |

**返回值**: `null`

---

### 2.2 投屏控制

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

### 2.3 媒体解析

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

### 2.4 设置管理

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
    friendly_name: '我的 Macast',
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

## 3. 事件监听

### 3.1 事件列表

| 事件名 | 触发时机 | Payload 类型 |
|--------|----------|--------------|
| `device_found` | 发现新设备 | `Device` |
| `device_lost` | 设备离线 | `{ id: string }` |
| `cast_state_changed` | 投屏状态变化 | `CastState` |
| `cast_error` | 投屏出错 | `{ message: string }` |

### 3.2 监听示例

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

## 4. 错误处理

### 4.1 错误类型

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

### 4.2 常见错误

| 错误信息 | 原因 | 处理建议 |
|----------|------|----------|
| `Device not found` | 设备 ID 不存在 | 刷新设备列表 |
| `File not found` | 本地文件不存在 | 提示用户检查文件路径 |
| `URL not reachable` | 网络链接不可达 | 提示用户检查网络 |
| `Unsupported format` | 不支持的媒体格式 | 提示用户选择支持的格式 |
| `Unknown command` | 命令不存在 | 检查命令拼写 |

### 4.3 错误处理示例

```typescript
import { message } from '@tauri-apps/plugin-dialog';

async function handleCast(deviceId: string, mediaUri: string) {
  try {
    await invoke('start_cast', {
      device_id: deviceId,
      media_uri: mediaUri
    });
    await message('投屏成功', { title: 'Macast', type: 'info' });
  } catch (error) {
    await message(`投屏失败: ${error}`, { title: 'Macast', type: 'error' });
  }
}
```

---

## 5. 完整示例

### 5.1 设备列表组件

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

### 5.2 投屏控制组件

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

## 6. TypeScript 类型定义

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

## 7. API 快速参考表

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_devices()` | - | `Device[]` | 获取设备列表 |
| `refresh_devices()` | - | `Device[]` | 触发扫描 |
| `set_default_device(device_id)` | `{ id: string }` | `null` | 设置默认设备 |
| `rename_device(device_id, name)` | `{ id, name }` | `null` | 重命名设备 |
| `remove_device(device_id)` | `{ id: string }` | `null` | 移除设备 |
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

| 事件 | Payload | 说明 |
|------|---------|------|
| `device_found` | `Device` | 发现新设备 |
| `device_lost` | `{ id }` | 设备离线 |
| `cast_state_changed` | `CastState` | 状态变化 |
| `cast_error` | `{ message }` | 投屏错误 |
