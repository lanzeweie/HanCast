#!/usr/bin/env node
/**
 * sync-version.cjs
 * 以 package.json 为单一真相源（SSOT），同步版本号到所有项目文件。
 *
 * 用法：
 *   node scripts/sync-version.cjs          # 同步当前版本
 *   node scripts/sync-version.cjs 2.0.0    # 设置新版本并同步
 */

const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')

// ── 读取当前版本 ──
const pkgPath = path.join(ROOT, 'package.json')
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'))
const oldVersion = pkg.version

// ── 确定目标版本 ──
const newVersion = process.argv[2] || oldVersion

if (!/^\d+\.\d+\.\d+/.test(newVersion)) {
  console.error(`❌ 无效版本号: "${newVersion}"，格式应为 x.y.z`)
  process.exit(1)
}

if (process.argv[2]) {
  // 写回 package.json
  pkg.version = newVersion
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n', 'utf-8')
  console.log(`📝 package.json: ${oldVersion} → ${newVersion}`)
} else {
  console.log(`📦 当前版本: ${newVersion}`)
}

// ── 同步目标 ──
const targets = [
  {
    file: 'src-tauri/tauri.conf.json',
    replace: (content) => content.replace(
      /("version"\s*:\s*")[\d.]+(")/,
      `$1${newVersion}$2`
    ),
  },
  {
    file: 'src-tauri/Cargo.toml',
    replace: (content) => content.replace(
      /^(version\s*=\s*")[\d.]+(")/m,
      `$1${newVersion}$2`
    ),
  },
  {
    file: 'hancast-backend/pyproject.toml',
    replace: (content) => content.replace(
      /^(version\s*=\s*")[\d.]+(")/m,
      `$1${newVersion}$2`
    ),
  },
  {
    file: 'hancast-backend/hancast_sidecar/utils/config.py',
    replace: (content) => content.replace(
      /(self\.version\s*=\s*")[\d.]+(")/,
      `$1${newVersion}$2`
    ),
  },
  {
    file: 'src/api/commands.ts',
    replace: (content) => {
      // MOCK_SETTINGS 的 version
      content = content.replace(
        /(version:\s*')[\d.]+(')/g,
        `$1${newVersion}$2`
      )
      // mock check_update 的 current/latest
      content = content.replace(
        /(current:\s*')[\d.]+(')/g,
        `$1${newVersion}$2`
      )
      content = content.replace(
        /(latest:\s*')[\d.]+(')/g,
        `$1${newVersion}$2`
      )
      return content
    },
  },
  {
    file: 'src/stores/settings.ts',
    replace: (content) => content.replace(
      /(version:\s*')[\d.]+(')/,
      `$1${newVersion}$2`
    ),
  },
]

let changed = 0

for (const target of targets) {
  const filePath = path.join(ROOT, target.file)
  if (!fs.existsSync(filePath)) {
    console.log(`⚠️  跳过 ${target.file}（文件不存在）`)
    continue
  }

  const original = fs.readFileSync(filePath, 'utf-8')
  const updated = target.replace(original)

  if (updated !== original) {
    fs.writeFileSync(filePath, updated, 'utf-8')
    console.log(`✅ ${target.file}`)
    changed++
  } else {
    console.log(`⏭️  ${target.file}（已是最新）`)
  }
}

console.log(`\n🎉 版本同步完成: ${newVersion}，更新了 ${changed} 个文件`)
