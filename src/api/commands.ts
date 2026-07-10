/**
 * Tauri invoke command wrappers.
 * These are placeholders — real implementations will call the Rust backend.
 */
import type { Device } from '@/types/device'
import type { MediaInfo } from '@/types/media'
import type { CastState, CastUrlInfo } from '@/types/cast'
import type { AppSettings } from '@/types/settings'
import type { GuardDevicesResponse, GuardSettings } from '@/types/guard'
import type { UpdateInfo } from '@/types/update'

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
  usn: 'hancast-uuid-001',
  friendly_name: 'HanCast',
  version: '2.0.1',
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
    case 'get_autostart':
      return false as T
    case 'set_autostart':
      return undefined as T
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
    case 'get_guard_devices':
      return {
        trusted: [],
        blacklisted: [],
      } as T
    case 'get_guard_settings':
      return {
        enabled: true,
        confirm_timeout: 15,
      } as T
    case 'respond_cast_confirm':
      return true as T
    case 'remove_guard_device':
      return true as T
    case 'set_guard_policy':
      return true as T
    case 'save_guard_settings':
      return {} as T
    case 'check_update':
      return {
        has_update: false,
        current: '2.0.1',
        latest: '2.0.1',
        url: '',
        body: '',
        source: 'github',
      } as T
    case 'ignore_update_version':
      return true as T
    case 'export_logs':
      return true as T
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

// Cast control — all commands accept optional deviceId for multi-device support
export async function startCast(deviceId: string, mediaUri: string, mimeType?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('start_cast', { deviceId, mediaUri, mimeType })
}

export async function stopCast(deviceId?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('stop_cast', deviceId ? { deviceId } : {})
}

export async function pauseCast(deviceId?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('pause_cast', deviceId ? { deviceId } : {})
}

export async function resumeCast(deviceId?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('resume_cast', deviceId ? { deviceId } : {})
}

export async function seekCast(position: string, deviceId?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('seek_cast', { position, ...(deviceId ? { deviceId } : {}) })
}

export async function getCastState(deviceId?: string): Promise<CastState> {
  const invoke = await initInvoke()
  return invoke<CastState>('get_cast_state', deviceId ? { deviceId } : {})
}

export async function getCastUrl(deviceId?: string): Promise<CastUrlInfo> {
  const invoke = await initInvoke()
  return invoke<CastUrlInfo>('get_cast_url', deviceId ? { deviceId } : {})
}

export async function setVolume(volume: number, deviceId?: string): Promise<number> {
  const invoke = await initInvoke()
  return invoke<number>('set_volume', { volume, ...(deviceId ? { deviceId } : {}) })
}

export async function setMute(muted: boolean, deviceId?: string): Promise<void> {
  const invoke = await initInvoke()
  await invoke('set_mute', { muted, ...(deviceId ? { deviceId } : {}) })
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

// Autostart
export async function getAutostart(): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('get_autostart')
}

export async function setAutostart(enabled: boolean): Promise<void> {
  const invoke = await initInvoke()
  await invoke('set_autostart', { enabled })
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

// ── Device Guard ──

export async function respondCastConfirm(
  requestId: string,
  approved: boolean,
  policy: string,
): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('respond_cast_confirm', { requestId, approved, policy })
}

export async function getGuardDevices(): Promise<GuardDevicesResponse> {
  const invoke = await initInvoke()
  return invoke<GuardDevicesResponse>('get_guard_devices')
}

export async function removeGuardDevice(deviceKey: string): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('remove_guard_device', { deviceKey })
}

export async function setGuardPolicy(
  deviceKey: string,
  policy: 'trusted' | 'blacklisted',
): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('set_guard_policy', { deviceKey, policy })
}

export async function getGuardSettings(): Promise<GuardSettings> {
  const invoke = await initInvoke()
  return invoke<GuardSettings>('get_guard_settings')
}

export async function saveGuardSettings(settings: {
  enabled?: boolean
  confirm_timeout?: number
}): Promise<void> {
  const invoke = await initInvoke()
  await invoke('save_guard_settings', { settings })
}

// ── Export Logs ──

export async function exportLogs(): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('export_logs')
}

// ── Update Check ──

export async function checkUpdate(currentVersion: string, force?: boolean): Promise<UpdateInfo> {
  const invoke = await initInvoke()
  return invoke<UpdateInfo>('check_update', { currentVersion, force })
}

export async function ignoreUpdateVersion(version: string): Promise<boolean> {
  const invoke = await initInvoke()
  return invoke<boolean>('ignore_update_version', { version })
}
