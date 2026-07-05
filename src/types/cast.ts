import type { MediaInfo } from './media'

export interface CastState {
  status: 'idle' | 'connecting' | 'playing' | 'paused' | 'error'
  device_id: string | null
  media: MediaInfo | null
  position: number
  volume: number
  is_muted: boolean
}
