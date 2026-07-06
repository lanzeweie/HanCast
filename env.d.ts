/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Tauri 2.0 runtime globals
interface Window {
  __TAURI_INTERNALS__?: {
    metadata: {
      currentWindow: { label: string }
      currentWebview: { label: string }
    }
    invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
    transformCallback: (cb: Function) => number
  }
}
