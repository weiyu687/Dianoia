import { fileURLToPath } from 'node:url'
import { cpSync, createReadStream, existsSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const proxy = { '/api': 'http://127.0.0.1:8000' }
const pdfAssets = fileURLToPath(new URL('./node_modules/pdfjs-dist/', import.meta.url))
const pdfFolders = ['cmaps', 'standard_fonts']

export default defineConfig({
  plugins: [vue(), {
    name: 'dianoia-pdf-fonts',
    configureServer(server) {
      server.middlewares.use('/pdfjs', (request, response, next) => {
        const match = /^\/(cmaps|standard_fonts)\/([\w-][\w.-]+)$/.exec(request.url || '')
        if (!match) return next()
        const filename = resolve(pdfAssets, match[1], match[2])
        if (!existsSync(filename)) return next()
        response.setHeader('Content-Type', 'application/octet-stream')
        createReadStream(filename).pipe(response)
      })
    },
    writeBundle(options) {
      const target = resolve(options.dir, 'pdfjs')
      mkdirSync(target, { recursive: true })
      for (const folder of pdfFolders) cpSync(resolve(pdfAssets, folder), resolve(target, folder), { recursive: true })
    },
  }],
  optimizeDeps: { include: [
    'pdfjs-dist/legacy/build/pdf.mjs', 'pdfjs-dist/legacy/web/pdf_viewer.mjs',
    '@docx-editor.dev/vue', '@docx-editor.dev/i18n', '@docx-editor.dev/core/layout',
  ] },
  server: { proxy },
  preview: { proxy },
  build: {
    rollupOptions: {
      input: {
        teacher: fileURLToPath(new URL('./index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin/index.html', import.meta.url)),
      },
    },
  },
})
