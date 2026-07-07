import type { MediaInfo } from './media'

/** Single-device casting state */
export interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'stopped' | 'error'
  device_id: string | null
  device_name?: string
  media: MediaInfo | null
  position: number
  volume: number
  is_muted: boolean
  /** Current playback position in HH:MM:SS format from backend */
  positionTime: string
  /** Total duration in HH:MM:SS format from backend */
  durationTime: string
}

/** A casting session bound to a specific device */
export interface CastSession {
  device_id: string
  device_name: string
  status: CastState['status']
  media: MediaInfo | null
  position: number
  volume: number
  is_muted: boolean
  positionTime: string
  durationTime: string
}

/** Response from get_cast_url command */
export interface CastUrlInfo {
  url: string
  title: string
  duration: string   // HH:MM:SS
  position: string   // HH:MM:SS
  status: string     // PLAYING / PAUSED / STOPPED
}

/** Create a blank session for a device */
export function createSession(deviceId: string, deviceName: string): CastSession {
  return {
    device_id: deviceId,
    device_name: deviceName,
    status: 'connecting',
    media: null,
    position: 0,
    volume: 80,
    is_muted: false,
    positionTime: '00:00:00',
    durationTime: '00:00:00',
  }
}
