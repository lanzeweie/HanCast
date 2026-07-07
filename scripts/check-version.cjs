#!/usr/bin/env node
/**
 * Check that all version fields are in sync with tauri.conf.json (source of truth).
 * Run: node scripts/check-version.js
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')

// Source of truth
const tauriConf = JSON.parse(fs.readFileSync(path.join(ROOT, 'src-tauri/tauri.conf.json'), 'utf8'))
const expected = tauriConf.version

const checks = [
  { file: 'package.json', get: f => JSON.parse(fs.readFileSync(f, 'utf8')).version },
  { file: 'src-tauri/Cargo.toml', get: f => fs.readFileSync(f, 'utf8').match(/^version\s*=\s*"(.+?)"/m)?.[1] },
  { file: 'macast-backend/pyproject.toml', get: f => fs.readFileSync(f, 'utf8').match(/^version\s*=\s*"(.+?)"/m)?.[1] },
]

let ok = true
for (const { file, get } of checks) {
  const fullPath = path.join(ROOT, file)
  const ver = get(fullPath)
  if (ver !== expected) {
    console.error(`MISMATCH  ${file}: "${ver}" (expected "${expected}")`)
    ok = false
  } else {
    console.log(`OK        ${file}: ${ver}`)
  }
}

if (!ok) {
  console.error('\nVersion mismatch! Update all files to match src-tauri/tauri.conf.json')
  process.exit(1)
}
