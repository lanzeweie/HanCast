export interface Device {
  id: string
  name: string
  type: 'tv' | 'speaker' | 'box' | 'unknown'
  ip: string
  port: number
  status: 'online' | 'busy' | 'offline'
  is_default: boolean
  manufacturer?: string
  model_name?: string
  udn: string
}
