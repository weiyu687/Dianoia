<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist/legacy/build/pdf.mjs'
import worker from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = worker
const props = defineProps({ src: { type: String, required: true }, page: { type: Number, default: 1 } })
const emit = defineEmits(['update:page'])
const canvas = ref(null)
const wrapper = ref(null)
const total = ref(0)
const error = ref('')
const busy = ref(true)
let task
let document
let rendering
let observer
let currentLoad = 0
let currentRender = 0

async function paint() {
  if (!document || !canvas.value) return
  const request = ++currentRender
  rendering?.cancel()
  try {
    const page = await document.getPage(Math.min(Math.max(1, props.page), total.value))
    if (request !== currentRender || !canvas.value) return
    const size = page.getViewport({ scale: 1 })
    const targetWidth = Math.min(860, Math.max(100, wrapper.value.clientWidth - 28))
    const cssScale = targetWidth / size.width
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    const viewport = page.getViewport({ scale: cssScale * ratio })
    const surface = canvas.value
    surface.width = Math.ceil(viewport.width)
    surface.height = Math.ceil(viewport.height)
    surface.style.width = `${viewport.width / ratio}px`
    surface.style.height = `${viewport.height / ratio}px`
    rendering = page.render({ canvas: surface, viewport })
    await rendering.promise
  } catch (failure) {
    if (request === currentRender && failure.name !== 'RenderingCancelledException') error.value = '当前页无法渲染。'
  }
}

async function load() {
  const request = ++currentLoad
  ++currentRender
  rendering?.cancel()
  task?.destroy().catch(() => {})
  document = null
  total.value = 0
  busy.value = true
  error.value = ''
  try {
    task = getDocument({
      url: props.src, useSystemFonts: true, isEvalSupported: false,
      cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/',
    })
    const loaded = await task.promise
    if (request !== currentLoad) return
    document = loaded
    total.value = loaded.numPages
    await paint()
  } catch {
    if (request === currentLoad) error.value = '无法打开 PDF。请刷新或下载原文件。'
  } finally {
    if (request === currentLoad) busy.value = false
  }
}

function jump(value) {
  const number = Number(value)
  if (!Number.isInteger(number) || number < 1 || number > total.value) return
  emit('update:page', number)
}
watch(() => props.src, load)
watch(() => props.page, paint)
onMounted(() => {
  observer = new ResizeObserver(() => paint())
  observer.observe(wrapper.value)
  load()
})
onBeforeUnmount(() => {
  ++currentLoad
  ++currentRender
  observer?.disconnect()
  rendering?.cancel()
  task?.destroy().catch(() => {})
})
</script>

<template>
  <div class="pdf-viewer">
    <div class="pdf-toolbar">
      <strong>PDF 预览</strong><div class="actions">
        <button class="button subtle icon-only" aria-label="上一页" :disabled="page <= 1" @click="jump(page - 1)"><ChevronLeft :size="17" /></button>
        <input type="number" aria-label="跳转页码" :value="page" min="1" :max="total || 1" @change="jump($event.target.value)" @keydown.enter.prevent="jump($event.target.value)">
        <span class="muted">/ {{ total || '—' }}</span>
        <button class="button subtle icon-only" aria-label="下一页" :disabled="page >= total" @click="jump(page + 1)"><ChevronRight :size="17" /></button>
      </div>
    </div>
    <div ref="wrapper" class="pdf-surface">
      <p v-if="busy" role="status">正在渲染 PDF</p>
      <p v-if="error" class="error" role="alert">{{ error }} <a class="text-link" :href="src" target="_blank" rel="noopener">在浏览器中打开</a></p>
      <canvas v-show="!busy && !error" ref="canvas" :aria-label="`PDF 第 ${page} 页，共 ${total} 页`" />
    </div>
  </div>
</template>
