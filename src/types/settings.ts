/** 接收协议：设备以哪套身份对外 */
export type Protocol = 'dlna' | 'nva'

export interface AppSettings {
  usn: string
  friendly_name: string
  protocol: Protocol
  version: string
  media_port: number
  default_device: string | null
  settings: Record<string, unknown>
}

export interface DeviceLostEvent {
  id: string
}

export interface CastErrorEvent {
  message: string
}
