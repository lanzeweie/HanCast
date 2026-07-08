/** A device entry in the guard trust/blacklist */
export interface GuardDevice {
  udn: string
  ip: string
  friendly_name: string
  policy: 'trusted' | 'blacklisted'
  created_at: string
  last_seen_at: string
  cast_count: number
}

/** Response from get_guard_devices */
export interface GuardDevicesResponse {
  trusted: GuardDevice[]
  blacklisted: GuardDevice[]
}

/** Guard feature settings */
export interface GuardSettings {
  enabled: boolean
  confirm_timeout: number // seconds
}

/** Incoming cast confirmation request event payload */
export interface CastConfirmRequest {
  request_id: string
  device: {
    ip: string
    udn: string
    friendly_name: string
    model_name: string
  }
  timeout: number
}
