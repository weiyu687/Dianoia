<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { Editor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { ArrowLeft, Download, Eye, Plus, Save, Sparkles } from 'lucide-vue-next'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { api, download } from '../api'
import LessonOutline from '../components/LessonOutline.vue'
import PdfViewer from '../components/PdfViewer.vue'
import { InlineWriting, suggestionKey } from '../components/inlineWriting'

const id = String(useRoute().params.id)
const lesson = ref(null)
const active = ref('')
const editor = shallowRef(null)
const changed = ref(false)
const saving = ref(false)
const status = ref('')
const error = ref('')
const writing = ref(false)
const hasSuggestion = ref(false)
const mode = ref('')
const instruction = ref('')
const rewriteResult = ref('')
const preview = ref(false)
const previewPage = ref(1)
let operation = 0
let loadingSection = false
let rewriteDocument = null

function search(sections, id) {
  for (const section of sections) {
    if (section.id === id) return section
    const result = search(section.children, id)
    if (result) return result
  }
  return null
}
const current = computed(() => lesson.value && search(lesson.value.sections, active.value))

function textDocument(text) {
  return { type: 'doc', content: text.split('\n').map((line) => ({
    type: 'paragraph', ...(line ? { content: [{ type: 'text', text: line }] } : {}),
  })) }
}

function clearWriting() {
  operation += 1
  writing.value = false
  rewriteResult.value = ''
  mode.value = ''
  const view = editor.value?.view
  if (view && suggestionKey.getState(view.state)) view.dispatch(view.state.tr.setMeta(suggestionKey, null))
}

function select(id) {
  if (id === active.value) return
  clearWriting()
  active.value = id
  loadingSection = true
  editor.value.commands.setContent(textDocument(current.value.content), { emitUpdate: false })
  loadingSection = false
}

function acceptSuggestion() {
  const view = editor.value.view
  const item = suggestionKey.getState(view.state)
  if (!item) return
  const transaction = view.state.tr.insertText(item.text, item.position).setMeta(suggestionKey, null).scrollIntoView()
  view.dispatch(transaction)
  editor.value.commands.focus()
  status.value = '已采纳续写'
}

async function ask(type, request = '') {
  if (!current.value || !editor.value) return
  const instance = editor.value
  const { doc, selection } = instance.state
  const currentId = active.value
  const position = selection.to
  const requestId = ++operation
  if (suggestionKey.getState(instance.state)) instance.view.dispatch(instance.state.tr.setMeta(suggestionKey, null))
  const before = type === 'rewrite' ? instance.getText().slice(0, 14000) : doc.textBetween(0, position, '\n').slice(-14000)
  const after = type === 'rewrite' ? '' : doc.textBetween(position, doc.content.size, '\n').slice(0, 14000)
  writing.value = true
  rewriteResult.value = ''
  error.value = ''
  status.value = type === 'rewrite' ? '正在重写当前小节' : '正在生成续写'
  try {
    const result = await api('/ai/writing', { method: 'POST', body: {
      lesson_id: id, section: current.value.title, mode: type, before, after, instruction: request,
    } })
    if (requestId !== operation) return
    if (instance.isDestroyed || currentId !== active.value || doc !== instance.state.doc
        || (type === 'continue' && position !== instance.state.selection.to)) {
      status.value = '编辑位置已变化，请重新生成'
      return
    }
    if (type === 'rewrite') {
      rewriteDocument = doc
      rewriteResult.value = result.text
    } else {
      mode.value = ''
      instance.view.dispatch(instance.state.tr.setMeta(suggestionKey, { position, text: result.text, id: requestId }))
      instance.commands.focus()
    }
    status.value = type === 'rewrite' ? '重写结果已就绪' : 'Tab 采纳 · Esc 取消'
  } catch (failure) {
    if (requestId === operation) { error.value = failure.message; status.value = '' }
  } finally {
    if (requestId === operation) writing.value = false
  }
}

function applyRewrite() {
  if (editor.value.state.doc !== rewriteDocument) {
    error.value = '小节已被修改，请重新生成重写结果'
    clearWriting()
    return
  }
  editor.value.commands.setContent(textDocument(rewriteResult.value))
  clearWriting()
  status.value = '已应用重写'
}

function markChanged() { changed.value = true; status.value = '有未保存的修改' }

onMounted(async () => {
  try {
    lesson.value = await api(`/lessons/${id}`)
    active.value = lesson.value.sections[0].id
    editor.value = new Editor({
      extensions: [
        StarterKit.configure({
          bold: false, italic: false, strike: false, code: false, link: false, underline: false,
          blockquote: false, bulletList: false, orderedList: false, listItem: false,
          codeBlock: false, horizontalRule: false, heading: false,
        }),
        InlineWriting,
      ],
      content: textDocument(current.value.content),
      editorProps: {
        attributes: { role: 'textbox', 'aria-label': '小节正文', 'aria-multiline': 'true' },
        handleKeyDown(view, event) {
          if (event.isComposing || view.composing || event.keyCode === 229) return false
          if (event.altKey && event.code === 'Backslash' && !event.ctrlKey && !event.metaKey && !event.repeat) {
            event.preventDefault()
            ask('continue')
            return true
          }
          if (event.key === 'Tab' && suggestionKey.getState(view.state)) {
            event.preventDefault()
            acceptSuggestion()
            return true
          }
          if (event.key === 'Escape' && (suggestionKey.getState(view.state) || writing.value || mode.value)) {
            event.preventDefault()
            clearWriting()
            status.value = ''
            return true
          }
          return false
        },
      },
      onTransaction({ editor }) { hasSuggestion.value = Boolean(suggestionKey.getState(editor.state)) },
      onUpdate({ editor }) {
        if (loadingSection) return
        current.value.content = editor.getText({ blockSeparator: '\n' })
        markChanged()
      },
    })
    status.value = '已保存'
  } catch (failure) { error.value = failure.message }
})

function preventUnload(event) {
  if (!changed.value) return
  event.preventDefault()
  event.returnValue = ''
}
window.addEventListener('beforeunload', preventUnload)
onBeforeRouteLeave(() => !changed.value || window.confirm('当前有未保存的教案修改，确定离开？'))
onBeforeUnmount(() => {
  operation += 1
  editor.value?.destroy()
  window.removeEventListener('beforeunload', preventUnload)
})

async function save() {
  if (!changed.value || saving.value) return !changed.value
  saving.value = true
  error.value = ''
  const body = JSON.parse(JSON.stringify(lesson.value))
  try {
    const saved = await api(`/lessons/${id}`, { method: 'PUT', body })
    const unchanged = JSON.stringify(lesson.value.sections) === JSON.stringify(body.sections) && lesson.value.title === body.title
    lesson.value.revision = saved.revision
    changed.value = !unchanged
    status.value = unchanged ? '已保存' : '有未保存的修改'
    return unchanged
  } catch (failure) {
    error.value = failure.message
    return false
  } finally { saving.value = false }
}

async function showPreview() {
  if (preview.value) { preview.value = false; return }
  if (await save()) { previewPage.value = 1; preview.value = true }
}

async function exportFile(format) {
  try {
    if (await save()) await download(`/lessons/${id}/export/${format}`, `${lesson.value.title}.${format}`)
  } catch (failure) { error.value = failure.message }
}

function addSubsection() {
  const child = { id: crypto.randomUUID(), title: '新小节', content: '', children: [] }
  current.value.children.push(child)
  markChanged()
  select(child.id)
}
</script>

<template>
  <div class="page lesson-page">
    <RouterLink class="text-link back-link" to="/lessons"><ArrowLeft :size="16" /> 返回教案管理</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="lesson && editor">
      <header class="page-heading">
        <div class="editor-title"><input v-model="lesson.title" aria-label="教案名称" maxlength="160" @input="markChanged"><p>v{{ lesson.revision }} · <span role="status">{{ status }}</span></p></div>
        <div class="actions">
          <button class="button secondary" @click="showPreview"><Eye :size="17" /> {{ preview ? '返回编辑' : 'PDF 预览' }}</button>
          <details class="row-menu export-menu"><summary class="button secondary"><Download :size="17" /> 导出</summary><div><button @click="exportFile('docx')">Word (.docx)</button><button @click="exportFile('doc')">旧版 Word (.doc)</button><button @click="exportFile('pdf')">PDF (.pdf)</button></div></details>
          <button class="button primary" :disabled="saving" @click="save"><Save :size="17" /> {{ saving ? '正在保存' : '保存' }}</button>
        </div>
      </header>
      <PdfViewer v-if="preview" :src="`/api/lessons/${id}/export/pdf?inline=true&v=${lesson.revision}`" v-model:page="previewPage" />
      <div v-show="!preview" class="document-layout">
        <nav class="panel outline-panel" aria-label="教案章节">
          <div class="section-heading"><h2>教案目录</h2><button class="button subtle icon-only" aria-label="添加子小节" @click="addSubsection"><Plus :size="16" /></button></div>
          <LessonOutline :sections="lesson.sections" :active="active" @select="select" />
        </nav>
        <article class="panel editor-paper">
          <div class="editor-toolbar">
            <button class="button subtle" @mousedown.prevent @click="mode = mode === 'continue' ? '' : 'continue'; instruction = ''"><Sparkles :size="16" /> AI 续写 <kbd>Alt+\</kbd></button>
            <button class="button subtle" @mousedown.prevent @click="mode = mode === 'rewrite' ? '' : 'rewrite'; instruction = ''">重写本节</button>
            <button v-if="hasSuggestion" class="button primary" @mousedown.prevent @click="acceptSuggestion">采纳 <kbd>Tab</kbd></button>
            <button v-if="hasSuggestion || writing" class="button subtle" @mousedown.prevent @click="clearWriting">取消 <kbd>Esc</kbd></button>
          </div>
          <form v-if="mode" class="writing-panel stack" @submit.prevent="ask(mode, instruction)">
            <label>{{ mode === 'rewrite' ? '重写要求' : '续写要求' }}<input v-model="instruction" maxlength="2000" placeholder="输入对这一段的要求"></label>
            <div class="actions"><button class="button primary" type="submit" :disabled="writing">{{ writing ? '正在生成' : '生成建议' }}</button><button type="button" class="button subtle" @click="clearWriting">关闭</button></div>
            <template v-if="rewriteResult"><div class="rewrite-result">{{ rewriteResult }}</div><button type="button" class="button secondary" @click="applyRewrite">应用到本节</button></template>
          </form>
          <label class="section-title"><span class="sr-only">小节标题</span><input v-model="current.title" maxlength="160" @input="markChanged"></label>
          <EditorContent :editor="editor" />
        </article>
      </div>
    </template>
  </div>
</template>
