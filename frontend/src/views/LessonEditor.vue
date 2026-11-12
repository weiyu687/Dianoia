<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  DocxEditorContent, DocxEditorContentControl, DocxEditorContextMenu, DocxEditorEquation,
  DocxEditorHyperLink, DocxEditorLoading, DocxEditorOpenFailure, DocxEditorRoot,
  DocxEditorToolbar, DocxEditorViewport, LocaleProvider,
} from '@docx-editor.dev/vue'
import { zhCN } from '@docx-editor.dev/i18n'
import { setHarfBuzzWasmUrl } from '@docx-editor.dev/core/layout'
import harfBuzzWasm from '@docx-editor.dev/core/harfbuzz.wasm?url'
import '@docx-editor.dev/vue/styles.css'
import { ArrowLeft, Download, Eye, Save } from 'lucide-vue-next'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { api, download } from '../api'
import PdfViewer from '../components/PdfViewer.vue'
import { theme } from '../session'
import { useLessonWriting, writingOptions } from '../lessonWriting'

setHarfBuzzWasmUrl(harfBuzzWasm)

const id = String(useRoute().params.id)
const lesson = ref(null)
const documentBytes = shallowRef(null)
const editor = shallowRef(null)
const editable = ref(false)
const loading = ref(true)
const changed = ref(false)
const saving = ref(false)
const notice = ref('')
const error = ref('')
const preview = ref(false)
const previewPage = ref(1)
const page = ref(1)
const totalPages = ref(0)
const pageInput = ref(null)
const canvas = ref(null)
const chineseFonts = { supportedFamilies: [
  '宋体', '黑体', '仿宋', '楷体', '微软雅黑', '等线', '华文中宋', '华文楷体', '思源宋体', '思源黑体',
] }
const writing = useLessonWriting({ editor, canvas, id, title: () => lesson.value.title, notice })
const { mode, action, instruction, instructionInput, suggestion, busy: writingBusy, error: writingError, anchor } = writing
let editVersion = 0
let unsubscribe = null

onMounted(async () => {
  window.addEventListener('beforeunload', preventUnload)
  try {
    const info = await api(`/lessons/${id}`)
    const response = await api(`/lessons/${id}/document?revision=${info.revision}`, { binary: true })
    documentBytes.value = await response.arrayBuffer()
    lesson.value = info
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function editorReady(instance) {
  editor.value = instance
  editable.value = instance.snapshot().editable
  unsubscribe?.()
  unsubscribe = instance.on('selectionChange', () => {
    updatePage()
    writing.scheduleSelection()
  })
  updatePage()
}

function updatePage() {
  const instance = editor.value
  if (!instance) return
  page.value = instance.getCurrentPage('viewport') || 1
  totalPages.value = instance.getTotalPages()
}

function jumpPage() {
  const input = pageInput.value
  const destination = Number(input.value)
  if (Number.isInteger(destination) && destination >= 1 && destination <= totalPages.value) {
    editor.value?.scrollToPage(destination)
  }
  updatePage()
  input.value = page.value
}

function preventUnload(event) {
  if (!changed.value) return
  event.preventDefault()
  event.returnValue = ''
}
onBeforeRouteLeave(() => !changed.value || window.confirm('当前有未保存的教案修改，确定离开？'))
onBeforeUnmount(() => {
  unsubscribe?.()
  window.removeEventListener('beforeunload', preventUnload)
})

function markChanged() {
  editVersion += 1
  changed.value = true
  notice.value = ''
}
function documentChanged(change) {
  if (change.source === 'load') return
  markChanged()
  updatePage()
  writing.documentChanged(change)
}

async function save() {
  if (!changed.value || saving.value) return !changed.value
  const title = lesson.value.title.trim()
  if (!title) {
    error.value = '教案名称不能为空'
    return false
  }
  saving.value = true
  error.value = ''
  const version = editVersion
  try {
    const content = await editor.value.save()
    if (!content) throw new Error('无法保存 Word 正文，请重新打开教案')
    const body = new FormData()
    body.append('file', new Blob([content], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }), 'lesson.docx')
    body.append('title', title)
    body.append('revision', lesson.value.revision)
    const saved = await api(`/lessons/${id}/document`, { method: 'PUT', body })
    lesson.value.revision = saved.revision
    changed.value = version !== editVersion
    if (!changed.value) lesson.value.title = saved.title
    return !changed.value
  } catch (failure) {
    error.value = failure.message
    return false
  } finally { saving.value = false }
}

async function showPreview() {
  if (preview.value) { preview.value = false; return }
  if (await save()) {
    writing.clear()
    previewPage.value = 1
    preview.value = true
  }
}

async function exportFile(format, event) {
  event.target.closest('details').open = false
  try {
    if (await save()) await download(`/lessons/${id}/export/${format}`, `${lesson.value.title}.${format}`)
  } catch (failure) { error.value = failure.message }
}

</script>

<template>
  <div class="page lesson-page">
    <RouterLink class="text-link back-link" to="/lessons"><ArrowLeft :size="16" /> 返回教案管理</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state" role="status">正在加载教案</p>
    <template v-if="lesson">
      <header class="page-heading">
        <div class="editor-title">
          <input v-model="lesson.title" aria-label="教案名称" maxlength="160" :disabled="!editable || preview" @input="markChanged">
          <p role="status">v{{ lesson.revision }} · {{ changed ? '有未保存的修改' : '已保存' }}</p>
        </div>
        <div class="actions">
          <button class="button secondary" :disabled="saving" @click="showPreview"><Eye :size="17" /> {{ preview ? '返回编辑' : 'PDF 预览' }}</button>
          <details class="row-menu export-menu"><summary class="button secondary"><Download :size="17" /> 导出</summary>
            <div><button :disabled="saving" @click="exportFile('docx', $event)">Word (.docx)</button><button :disabled="saving" @click="exportFile('doc', $event)">旧版 Word (.doc)</button><button :disabled="saving" @click="exportFile('pdf', $event)">PDF (.pdf)</button></div>
          </details>
          <button class="button primary" :disabled="saving || !changed || !editable" @click="save"><Save :size="17" /> {{ saving ? '正在保存' : '保存' }}</button>
        </div>
      </header>
      <PdfViewer v-if="preview" :src="`/api/lessons/${id}/export/pdf?inline=true&v=${lesson.revision}`" v-model:page="previewPage" />
      <section v-show="!preview" class="word-editor" aria-label="Word 教案编辑器" @keydown.capture="writing.keydown">
        <LocaleProvider :i18n="zhCN">
          <DocxEditorRoot :document="documentBytes" locale="zh-CN" :color-mode="theme" :fonts="chineseFonts" @ready="editorReady" @change="documentChanged">
            <div class="word-toolbar">
              <DocxEditorToolbar>
                <DocxEditorToolbar.Group id="insert" label="插入" after="text" :priority="75">
                  <DocxEditorToolbar.ImageInsert />
                  <DocxEditorToolbar.TableInsert />
                </DocxEditorToolbar.Group>
              </DocxEditorToolbar>
            </div>
            <div class="word-actions">
              <form v-if="totalPages" class="word-page-number" @submit.prevent="jumpPage">
                <label>页 <input ref="pageInput" :value="page" aria-label="跳转到教案页码" type="number" min="1" :max="totalPages" @change="jumpPage"></label>
                <span>/ {{ totalPages }}</span>
              </form>
            </div>
            <p v-if="notice" class="word-notice" role="status">{{ notice }}</p>
            <div ref="canvas" class="word-canvas" @pointerdown.capture="writing.pointerDown" @scroll.capture="updatePage(); writing.position()">
              <DocxEditorViewport class="word-viewport">
                <DocxEditorContent />
                <DocxEditorHyperLink />
                <DocxEditorContextMenu />
                <DocxEditorEquation />
                <DocxEditorContentControl />
              </DocxEditorViewport>
              <DocxEditorLoading overlay />
              <div v-if="mode && anchor" class="lesson-writing" :style="anchor" aria-label="光标处 AI 写作">
                <div v-if="suggestion" class="writing-suggestion" aria-live="polite">
                  <div class="writing-draft">
                    <template v-if="suggestion.blocks?.some(block => block.type === 'table')">
                      <template v-for="(block, index) in suggestion.blocks" :key="index">
                        <table v-if="block.type === 'table'">
                          <thead><tr><th v-for="(cell, col) in block.header" :key="col">{{ cell }}</th></tr></thead>
                          <tbody><tr v-for="(row, number) in block.rows" :key="number"><td v-for="(cell, col) in row" :key="col">{{ cell }}</td></tr></tbody>
                        </table>
                        <p v-else>{{ block.text }}</p>
                      </template>
                    </template>
                    <p v-else>{{ suggestion.text }}</p>
                  </div>
                  <div class="writing-controls">
                    <button class="button subtle" type="button" @mousedown.prevent @click="writing.apply">采纳 <kbd>Tab</kbd></button>
                    <button class="button subtle" type="button" @mousedown.prevent @click="writing.clear(true)">取消 <kbd>Esc</kbd></button>
                  </div>
                </div>
                <form v-else-if="action" class="writing-form" @submit.prevent="writing.generate">
                  <label>{{ action[0] }}<input ref="instructionInput" v-model="instruction" :required="action[0] === '按要求写'" maxlength="1900" placeholder="输入要求"></label>
                  <p v-if="writingError" class="error" role="alert">{{ writingError }}</p>
                  <div class="writing-controls">
                    <button class="button primary" type="submit" :disabled="writingBusy">{{ writingBusy ? '正在生成' : '生成' }}</button>
                    <button class="button subtle" type="button" @click="writing.clear(true)">取消</button>
                  </div>
                </form>
                <div v-else class="writing-options" aria-label="AI 写作选项">
                  <button v-for="option in writingOptions[mode]" :key="option[0]" class="button subtle" type="button" @mousedown.prevent @click="writing.choose(option)">{{ option[0] }}</button>
                </div>
              </div>
            </div>
            <DocxEditorOpenFailure />
          </DocxEditorRoot>
        </LocaleProvider>
      </section>
    </template>
  </div>
</template>
