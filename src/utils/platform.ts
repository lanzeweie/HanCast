/**
 * 运行平台判断。
 *
 * 仅用于文案与拖拽区域的细节差异（macOS 菜单栏 / 原生红绿灯），
 * 不参与业务逻辑。
 */
export const isMacOS =
  typeof navigator !== 'undefined' &&
  (/Mac/i.test(navigator.platform) || /Mac OS X/i.test(navigator.userAgent))