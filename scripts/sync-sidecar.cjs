#!/usr/bin/env node
/**
 * sync-sidecar.cjs
 * 将 Python Sidecar 源码目录同步到 src-tauri/，供 Tauri 资源打包。
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const SRC = path.join(ROOT, 'hancast-backend', 'hancast_sidecar')
const DEST = path.join(ROOT, 'src-tauri', 'hancast_sidecar')

if (!fs.existsSync(SRC)) {
  console.error(`❌ 找不到 hancast_sidecar 源码: ${SRC}`)
  process.exit(1)
}

// 确保目标目录存在
if (fs.existsSync(DEST)) {
  // 清除旧内容（保留空目录）
  const entries = fs.readdirSync(DEST)
  entries.forEach((entry) => {
    const entryPath = path.join(DEST, entry)
    if (fs.statSync(entryPath).isDirectory()) {
      recursiveRmdir(entryPath)
    } else {
      fs.rmSync(entryPath)
    }
  })
} else {
  fs.mkdirSync(DEST, { recursive: true })
}

// 复制所有文件和子目录（排除 __pycache__、.pyc 等）
const ignore = [/__pycache__/, /\.py[cod]$/, /\.egg-info/, /\.pytest_cache/, /\.mypy_cache/]
copyDir(SRC, DEST, ignore)

console.log(`✅ 同步 hancast_sidecar → src-tauri/hancast_sidecar`)

function copyDir(src, dest, ignoreList) {
  const entries = fs.readdirSync(src, { withFileTypes: true })
  entries.forEach((entry) => {
    const srcPath = path.join(src, entry.name)
    const destPath = path.join(dest, entry.name)

    // 跳过忽略模式
    if (ignoreList.some(re => re.test(entry.name))) return

    if (entry.isDirectory()) {
      if (!fs.existsSync(destPath)) fs.mkdirSync(destPath, { recursive: true })
      copyDir(srcPath, destPath, ignoreList)
    } else {
      fs.copyFileSync(srcPath, destPath)
    }
  })
}

function recursiveRmdir(dir) {
  const entries = fs.readdirSync(dir)
  entries.forEach((entry) => {
    const entryPath = path.join(dir, entry)
    if (fs.statSync(entryPath).isDirectory()) {
      recursiveRmdir(entryPath)
    } else {
      fs.rmSync(entryPath)
    }
  })
}
