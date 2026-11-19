<script setup>
import { inject, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { TableKit } from '@tiptap/extension-table'
import { Bold, Italic, Underline, List, ListOrdered, Code2, ImagePlus, Table2, Sigma, Undo2, Redo2, Pilcrow } from 'lucide-vue-next'
import { api } from '../api'
import { BankImage, BankShortcuts, emptyDoc, FormulaNode, paragraphAfterTable } from '../questionBanks'
import FormulaEditor from './FormulaEditor.vue'
import Modal from './Modal.vue'

const props = defineProps({ modelValue: Object, bankId: { type: String, required: true }, label: { type: String, default: '正文' }, compact: Boolean })
const emit = defineEmits(['update:modelValue'])
const picker = ref(null)
const formula = ref(null)
const error = ref('')
const uploading = ref(false)
const trackUploads = inject('bank-image-uploads', null)
const editor = useEditor({
  content: props.modelValue || emptyDoc(),
  extensions: [StarterKit.configure({ heading: { levels: [2, 3] }, link: { openOnClick: false } }), Placeholder.configure({ placeholder: '在这里输入' + props.label + '…' }),
    TableKit.configure({ table: { resizable: true, cellMinWidth: 50 } }), BankImage, FormulaNode, BankShortcuts],
  editorProps: { attributes: { class: 'bank-prose', role: 'textbox', 'aria-label': props.label, 'aria-multiline': 'true' },
    handlePaste: (_, event) => {
      const image = Array.from(event.clipboardData?.files || []).find((f) => f.type.startsWith('image/'))
      if (image) { upload(image); return true }
      return false
    } },
  onUpdate: ({ editor: instance }) => emit('update:modelValue', instance.getJSON()),
})
watch(() => props.modelValue, (value) => {
  if (editor.value && JSON.stringify(value) !== JSON.stringify(editor.value.getJSON())) editor.value.commands.setContent(value || emptyDoc(), { emitUpdate: false })
}, { deep: true })
function command(name, ...args) { editor.value?.chain().focus()[name](...args).run() }
function openFormula(detail) {
  const selection = editor.value.state.selection
  formula.value = detail || { position: selection.from, end: selection.to, latex: '', display: false, fresh: true }
}
function applyFormula(latex) {
  const item = formula.value
  editor.value.chain().focus().insertContentAt({ from: item.position, to: item.fresh ? item.end : item.position + 1 },
    { type: 'formula', attrs: { latex, display: item.display } }).run()
  formula.value = null
}
async function upload(file) {
  if (!file || uploading.value) return
  trackUploads?.(1)
  uploading.value = true; error.value = ''
  try {
    const data = new FormData(); data.set('file', file); data.set('kind', 'image')
    const image = await api(`/question-banks/${props.bankId}/assets`, { method: 'POST', body: data })
    editor.value.chain().focus().insertContent([{ type: 'image', attrs: { assetId: image.id, alt: file.name } }, { type: 'paragraph' }]).run()
  } catch (failure) { error.value = failure.message }
  finally { uploading.value = false; trackUploads?.(-1); if (picker.value) picker.value.value = '' }
}
</script>

<template>
  <div class="bank-rich-editor" :class="{ compact }" @bank-open-formula="openFormula()" @bank-edit-formula="openFormula($event.detail)">
    <div v-if="editor" class="bank-rich-toolbar" role="toolbar" :aria-label="label + '格式工具'">
      <select aria-label="段落格式" :value="editor.isActive('heading', { level: 2 }) ? '2' : editor.isActive('heading', { level: 3 }) ? '3' : '0'"
        @change="$event.target.value === '0' ? command('setParagraph') : command('setHeading', { level: Number($event.target.value) })">
        <option value="0">正文</option><option value="2">标题</option><option value="3">小标题</option>
      </select>
      <button v-for="[name, icon, title, active] in [['toggleBold', Bold, '加粗', 'bold'], ['toggleItalic', Italic, '斜体', 'italic'], ['toggleUnderline', Underline, '下划线', 'underline'], ['toggleBulletList', List, '无序列表', 'bulletList'], ['toggleOrderedList', ListOrdered, '有序列表', 'orderedList'], ['toggleCodeBlock', Code2, '代码块', 'codeBlock']]"
        :key="name" type="button" :title="title" :aria-label="title" :aria-pressed="editor.isActive(active)" @mousedown.prevent @click="command(name)"><component :is="icon" :size="16" /></button>
      <span class="bank-toolbar-divider"></span>
      <button type="button" title="插入图片，也可粘贴图片" aria-label="插入图片" :disabled="uploading" @mousedown.prevent @click="picker.click()"><ImagePlus :size="17" /></button>
      <button type="button" title="插入公式 Ctrl/⌘+M，双击公式可编辑" aria-label="插入公式" @mousedown.prevent @click="openFormula()"><Sigma :size="18" /></button>
      <details class="bank-table-menu"><summary title="插入与编辑表格" aria-label="表格"><Table2 :size="17" /></summary>
        <div class="panel bank-menu-list"><button type="button" @mousedown.prevent @click="command('insertTable', { rows: 3, cols: 3, withHeaderRow: true })">插入 3×3 表格</button>
          <template v-if="editor.isActive('table')"><button v-for="[name, title] in [['addRowAfter','下方插入行'],['addColumnAfter','右侧插入列'],['deleteRow','删除行'],['deleteColumn','删除列'],['mergeOrSplit','合并 / 拆分单元格'],['toggleHeaderRow','切换表头'],['deleteTable','删除表格']]" :key="name" type="button" @mousedown.prevent @click="command(name)">{{ title }}</button></template>
        </div>
      </details>
      <button type="button" title="在表格后插入段落 Ctrl/⌘+Enter" aria-label="插入段落" @mousedown.prevent @click="paragraphAfterTable(editor)"><Pilcrow :size="16" /></button>
      <button type="button" title="撤销" aria-label="撤销" @mousedown.prevent @click="command('undo')"><Undo2 :size="16" /></button>
      <button type="button" title="重做" aria-label="重做" @mousedown.prevent @click="command('redo')"><Redo2 :size="16" /></button>
    </div>
    <EditorContent :editor="editor" />
    <input ref="picker" class="sr-only" type="file" accept="image/png,image/jpeg,image/webp" @change="upload($event.target.files[0])">
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="uploading" class="muted" role="status">正在上传图片…</p>
    <Modal :open="!!formula" :title="formula?.fresh ? '插入公式' : '编辑公式'" wide @close="formula = null">
      <template v-if="formula"><label class="bank-check"><input v-model="formula.display" type="checkbox">独立公式排版</label>
        <FormulaEditor :initial="formula.latex" :replace="!formula.fresh" @apply="applyFormula" /></template>
    </Modal>
  </div>
</template>
