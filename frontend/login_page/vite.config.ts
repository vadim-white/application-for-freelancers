import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'
import { palettes, tokensCss } from './src/styles/tokens.ts'

// Vite только предупреждает о чанке больше 500 kB и сборку не останавливает — здесь сборка падает
// (локально и в CI). Порог тот же, что у предупреждения Vite: 500 000 байт минифицированного JS
const MAX_CHUNK_BYTES = 500_000

function chunkSizeLimit(): Plugin {
  return {
    name: 'chunk-size-limit',
    apply: 'build',
    generateBundle: {
      // после хуков Vite: они дописывают в чанки карту preload, мерить надо итоговый код
      order: 'post',
      handler(_options, bundle) {
        const tooBig = Object.values(bundle)
          .filter((item) => item.type === 'chunk')
          .map((chunk) => ({
            name: chunk.fileName,
            bytes: new TextEncoder().encode(chunk.code).length
          }))
          .filter((chunk) => chunk.bytes > MAX_CHUNK_BYTES)
        if (tooBig.length > 0) {
          const list = tooBig.map((chunk) => `${chunk.name} ${chunk.bytes} байт`).join(', ')
          this.error(`JS-чанк больше ${MAX_CHUNK_BYTES} байт: ${list}`)
        }
      }
    }
  }
}

// CSS-переменные из src/styles/tokens.ts кладутся в <head> inline: они на месте до первой отрисовки
// и общий источник с themeOverrides Naive UI (там hex нужен в JS)
// public/favicon.svg не читает CSS-переменные, его цвета — hex из светлой палитры; сборка падает,
// если файл разошёлся с tokens.ts
function designTokens(): Plugin {
  return {
    name: 'design-tokens',
    buildStart() {
      const favicon = readFileSync(new URL('./public/favicon.svg', import.meta.url), 'utf8')
      const expected = [palettes.light.accent, palettes.light.text]
      const missing = expected.filter((hex) => !favicon.includes(`"${hex}"`))
      if (missing.length > 0) {
        this.error(`public/favicon.svg расходится с tokens.ts: нет цветов ${missing.join(', ')}`)
      }
    },
    transformIndexHtml: () => [
      {
        tag: 'style',
        attrs: { id: 'design-tokens' },
        children: tokensCss(),
        injectTo: 'head-prepend'
      }
    ]
  }
}

export default defineConfig({
  plugins: [vue(), designTokens(), chunkSizeLimit()],
  server: {
    port: 5173,
    hmr: {
      protocol: 'ws',
      host: 'localhost',
      port: 5173
    },
    // npm run dev: /api на gateway, браузер остаётся на одном origin (как с nginx).
    // По умолчанию gateway запущен локально без Docker; против compose (gateway наружу не опубликован) —
    // API_PROXY_TARGET=http://localhost:5173
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
    }
  }
})
