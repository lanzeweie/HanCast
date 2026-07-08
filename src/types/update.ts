/**
 * Update check result from backend
 */
export interface UpdateInfo {
  has_update: boolean
  current: string
  latest: string
  url: string
  body: string
  source: 'github' | 'gitee'
}

/**
 * Update modal state
 */
export type UpdateModalState = 'hidden' | 'checking' | 'available' | 'latest' | 'error'
