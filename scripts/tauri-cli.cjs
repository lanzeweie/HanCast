#!/usr/bin/env node
/**
 * tauri CLI 包装器（由 `npm run tauri ...` 调用）。
 *
 * 仅在 `dev` 子命令下叠加 tauri.dev.conf.json：
 * 开发模式由 uv 直接启动 Python sidecar、mpv 来自 PATH，
 * 不需要 bundle.externalBin / bundle.resources；但 Tauri 编译期会校验这些
 * 路径，干净检出（尚无 Nuitka 产物与 src-tauri/mpv）时会让 `tauri dev` 失败。
 *
 * `npm run tauri build` 不带这个配置，发布包仍然包含真实 sidecar 与 mpv。
 */
const { spawn } = require('child_process')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const args = process.argv.slice(2)
const cli = path.join(
  ROOT,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'tauri.cmd' : 'tauri'
)

if (args[0] === 'dev') {
  const config = ['--config', path.join(ROOT, 'src-tauri', 'tauri.dev.conf.json')]
  // `tauri dev -- ...` 之后的参数属于应用本身，配置参数必须插在 `--` 之前
  const sep = args.indexOf('--')
  if (sep === -1) {
    args.push(...config)
  } else {
    args.splice(sep, 0, ...config)
  }
}

const child = spawn(cli, args, {
  cwd: process.cwd(),
  stdio: 'inherit',
  shell: process.platform === 'win32',
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
  } else {
    process.exit(code ?? 1)
  }
})