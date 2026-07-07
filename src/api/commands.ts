/**
 * Tauri invoke command wrappers.
 * These are placeholders — real implementations will call the Rust backend.
 */
import type { Device } from '@/types/device'
import type { MediaInfo } from '@/types/media'
import type { CastState, CastUrlInfo } from '@/types/cast'
import type { AppSettings } from '@/types/settings'

// ── Helpers ──

let invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>

async function initInvoke() {
  if (invoke) return invoke
  try {
    // Check if Tauri runtime is actually available (not just the module)
    if (window.__TAURI_INTERNALS__?.metadata) {
      const core = await import('@tauri-apps/api/core')
      invoke = core.invoke
    } else {
      invoke = mockInvoke as unknown as typeof invoke
    }
  } catch {
    // Running outside Tauri (e.g. browser dev), use mock fallback
    invoke = mockInvoke as unknown as typeof invoke
  }
  return invoke
}

// ── Mock fallback for browser dev ──

const MOCK_DEVICES: Device[] = [
  {
    id: 'samsung-tv-001',
    name: 'Samsung TV',
    type: 'tv',
    ip: '192.168.1.100',
    port: 8008,
    status: 'online',
    is_default: true,
    manufacturer: 'Samsung',
    model_name: 'QN65Q80B',
    udn: 'uuid:samsung-tv-001',
  },
  {
    id: 'living-room-speaker',
    name: '客厅音箱',
    type: 'speaker',
    ip: '192.168.1.101',
    port: 8008,
    status: 'online',
    is_default: false,
    manufacturer: 'Sonos',
    model_name: 'One SL',
    udn: 'uuid:sonos-one-sl',
  },
  {
    id: 'study-speaker',
    name: '书房音箱',
    type: 'speaker',
    ip: '192.168.1.102',
    port: 8008,
    status: 'online',
    is_default: false,
    manufacturer: 'Sonos',
    model_name: 'One SL',
    udn: 'uuid:sonos-study',
  },
  {
    id: 'mi-box-001',
    name: '小米盒子',
    type: 'box',
    ip: '192.168.1.103',
    port: 8008,
    status: 'offline',
    is_default: false,
    manufacturer: 'Xiaomi',
    model_name: 'Mi Box S',
    udn: 'uuid:mi-box-001',
  },
]

const MOCK_SETTINGS: AppSettings = {
  usn: 'macast-uuid-001',
  friendly_name: 'Macast',
  version: '2.0.0',
  media_port: 8080,
  default_device: null,
  settings: {},
}

const MOCK_CAST_STATE: CastState = {
  status: 'idle',
  device_id: null,
  media: null,
  position: 0,
  volume: 80,
  is_muted: false,
  positionTime: '00:00:00',
  durationTime: '00:00:00',
}

async function mockInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  await new Promise((r) => setTimeout(r, 300))

  switch (cmd) {
    case 'get_devices':
    case 'refresh_devices':
      return MOCK_DEVICES as T
    case 'get_cast_state':
      return MOCK_CAST_STATE as T
    case 'get_settings':
      return MOCK_SETTINGS as T
    case 'parse_media_file': {
      const fp = String(args?.filePath ?? '')
      const name = fp.split(/[/\\]/).pop() ?? 'Unknown'
      const ext = name.split('.').pop()?.toLowerCase() ?? ''
      const mimeMap: Record<string, string> = {
        mp4: 'video/mp4', mkv: 'video/x-matroska', avi: 'video/x-msvideo',
        mov: 'video/quicktime', webm: 'video/webm', flv: 'video/x-flv',
        mp3: 'audio/mpeg', flac: 'audio/flac', wav: 'audio/wav',
        jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
        gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp',
      }
      return {
        media_type: 'file',
        uri: fp,
        title: name,
        mime_type: mimeMap[ext] ?? 'application/octet-stream',
        file_size: 1024 * 1024 * 50,
        duration: null,
        thumbnail: null,
      } as T
    }
    case 'parse_media_url':
      return {
        media_type: 'url',
        uri: args?.url ?? '',
        title: String(args?.url ?? '').split('/').pop() ?? 'Unknown',
        mime_type: 'video/mp4',
        file_size: null,
        duration: null,
        thumbnail: null,
      } as T
    case 'get_cast_url':
      return {
        url: 'http://example.com/video.mp4',
        title: 'Sample Video',
        duration: '00:05:30',
        position: '00:02:15',
        status: 'PLAYING',
      } as T
    default:
      return {} as T
  }
}

// ── Public API ──

// Device management
export async function getDevices(): Promise<Device[]> {
  const invoke = await initInvoke()
  return invoke<Device[]>('get_devices')
}

export async function refreshDevices(): Promise<Device[]> {
  const invoke = await initInvoke()
  return invoke<Device[]>('refresh_devices')
}

export async function setDefaultDevice(id: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('set_default_device', { id })
}

export async function renameDevice(id: string, name: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('rename_device', { id, name })
}

export async function removeDevice(id: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('remove_device', { id })
}

export async function hideDevice(id: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('hide_device', { id })
}

// Media parsing
export async function parseMediaFile(filePath: string): Promise<MediaInfo> {
  const invoke = await initInvoke()
  return invoke<MediaInfo>('parse_media_file', { filePath })
}

export async function parseMediaUrl(url: string): Promise<MediaInfo> {
  const invoke = await initInvoke()
  return invoke<MediaInfo>('parse_media_url', { url })
}

export async function resolveBilibili(url: string): Promise<MediaInfo> {
  const invoke = await initInvoke()
  return invoke<MediaInfo>('resolve_bilibili', { url })
}

// Cast control
export async function startCast(deviceId: string, mediaUri: string, mimeType?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('start_cast', { deviceId, mediaUri, mimeType })
}

export async function stopCast(): Promise<void> {
  const invoke = await initInvoke()
  await invoke('stop_cast')
}

export async function pauseCast(): Promise<void> {
  const invoke = await initInvoke()
  await invoke('pause_cast')
}

export async function resumeCast(): Promise<void> {
  const invoke = await initInvoke()
  await invoke('resume_cast')
}

export async function seekCast(position: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('seek_cast', { position })
}

export async function getCastState(): Promise<CastState> {
  const invoke = await initInvoke()
  return invoke<CastState>('get_cast_state')
}

export async function getCastUrl(): Promise<CastUrlInfo> {
  const invoke = await initInvoke()
  return invoke<CastUrlInfo>('get_cast_url')
}

export async function setVolume(volume: number): Promise<number> {
  const invoke = await initInvoke()
  return invoke<number>('set_volume', { volume })
}

export async function setMute(muted: boolean): Promise<void> {
  const invoke = await initInvoke()
  await invoke('set_mute', { muted })
}

// Settings
export async function getSettings(): Promise<AppSettings> {
  const invoke = await initInvoke()
  return invoke<AppSettings>('get_settings')
}

export async function saveSettings(settings: Partial<AppSettings>): Promise<void> {
  const invoke = await initInvoke()
  await invoke('save_settings', { settings })
}

// Window control
export async function minimizeWindow(): Promise<void> {
  try {
    const invoke = await initInvoke()
    await invoke('minimize_window')
  } catch {
    // Ignore in browser dev
  }
}

export async function closeWindow(): Promise<void> {
  try {
    const invoke = await initInvoke()
    await invoke('close_window')
  } catch {
    // Ignore in browser dev
  }
}
