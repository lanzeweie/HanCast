export interface AppSettings {
  usn: string
  friendly_name: string
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
