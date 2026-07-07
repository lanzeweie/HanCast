import type { MediaInfo } from './media'

export interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'stopped' | 'error'
  device_id: string | null
  media: MediaInfo | null
  position: number
  volume: number
  is_muted: boolean
  /** Current playback position in HH:MM:SS format from backend */
  positionTime: string
  /** Total duration in HH:MM:SS format from backend */
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
