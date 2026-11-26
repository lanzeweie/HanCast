/** macOS 应用防火墙状态（socketfilterfw --getglobalstate） */
export interface FirewallStatus {
  supported: boolean
  /** 0=关闭，1=开启，2=阻止所有传入连接 */
  state: number
  enabled: boolean
  blockAll: boolean
  stealth: boolean
  detail: string
}