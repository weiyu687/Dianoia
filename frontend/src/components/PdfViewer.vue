<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist/legacy/build/pdf.mjs'
import { EventBus, PDFLinkService, PDFViewer } from 'pdfjs-dist/legacy/web/pdf_viewer.mjs'
import worker from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/legacy/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = worker
const props = defineProps({ src: { type: String, required: true }, page: { type: Number, default: 1 } })
const emit = defineEmits(['update:page'])
const viewport = ref(null)
const pages = ref(null)
const total = ref(0)
const activePage = ref(1)
const error = ref('')
const busy = ref(true)
let task
let viewer
let linkService
let observer
let viewportEvents
let loaded = false

function load() {
  loaded = false
  total.value = 0
  busy.value = true
  error.value = ''
  viewer.setDocument(null)
  linkService.setDocument(null)
  task?.destroy().catch(() => {})
  const request = getDocument({
    url: props.src, useSystemFonts: true, isEvalSupported: false,
    cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/',
  })
  task = request
  request.promise.then(async (document) => {
    if (request !== task) return
    linkService.setDocument(document)
    viewer.setDocument(document)
    await viewer.firstPagePromise
  }).catch(() => {
    if (request !== task) return
    error.value = '无法打开 PDF。请刷新或下载原文件。'
    busy.value = false
  })
}

function jump(value) {
  const number = Number(value)
  if (!loaded || !Number.isInteger(number) || number < 1 || number > total.value) return
  viewer.scrollPageIntoView({ pageNumber: number })
}

function submitPage(event) {
  jump(event.target.value)
  event.target.value = activePage.value
}

watch(() => props.src, load)
watch(() => props.page, (number) => {
  if (number !== activePage.value) jump(number)
})
onMounted(() => {
  const eventBus = new EventBus()
  viewportEvents = new AbortController()
  linkService = new PDFLinkService({ eventBus })
  viewer = new PDFViewer({
    container: viewport.value, viewer: pages.value, eventBus, linkService,
    abortSignal: viewportEvents.signal, textLayerMode: 0, annotationMode: 0, maxCanvasPixels: 16777216,
  })
  linkService.setViewer(viewer)
  eventBus.on('pagesinit', () => {
    total.value = viewer.pagesCount
    loaded = true
    const destination = Math.max(1, Math.min(props.page, total.value))
    viewer.currentScaleValue = 'page-width'
    jump(destination)
    activePage.value = destination
    if (destination !== props.page) emit('update:page', destination)
    busy.value = false
  })
  eventBus.on('pagechanging', ({ pageNumber }) => {
    if (!loaded) return
    activePage.value = pageNumber
    emit('update:page', pageNumber)
  })
  observer = new ResizeObserver(() => {
    if (loaded && viewport.value.clientWidth) viewer.currentScaleValue = 'page-width'
  })
  observer.observe(viewport.value)
  load()
})
onBeforeUnmount(() => {
  loaded = false
  observer?.disconnect()
  viewer?.setDocument(null)
  viewportEvents?.abort()
  linkService?.setDocument(null)
  const pending = task
  task = null
  pending?.destroy().catch(() => {})
})
defineExpose({ jump })
</script>

<template>
  <div class="pdf-viewer">
    <div class="pdf-toolbar">
      <strong>PDF 预览</strong><div class="actions">
        <button class="button subtle icon-only" aria-label="上一页" :disabled="!total || activePage <= 1" @click="jump(activePage - 1)"><ChevronLeft :size="17" /></button>
        <input type="number" aria-label="跳转页码" :value="activePage" min="1" :max="total || 1" :disabled="!total" @change="submitPage" @keydown.enter.prevent="submitPage">
        <span class="muted">/ {{ total || '—' }}</span>
        <button class="button subtle icon-only" aria-label="下一页" :disabled="!total || activePage >= total" @click="jump(activePage + 1)"><ChevronRight :size="17" /></button>
      </div>
    </div>
    <div class="pdf-surface">
      <div ref="viewport" class="pdf-scroll" tabindex="0" role="region" aria-label="PDF 连续滚动预览">
        <div ref="pages" class="pdfViewer" />
      </div>
      <div v-if="busy || error" class="pdf-overlay">
        <p v-if="busy" role="status">正在加载 PDF</p>
        <p v-else class="error" role="alert">{{ error }} <a class="text-link" :href="src" target="_blank" rel="noopener">在浏览器中打开</a></p>
      </div>
    </div>
  </div>
</template>
