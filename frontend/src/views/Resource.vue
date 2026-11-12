<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Download, FileText, Plus, Save } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { api, download, formatSize } from '../api'
import ResourceOutline from '../components/ResourceOutline.vue'
import PdfViewer from '../components/PdfViewer.vue'

const id = String(useRoute().params.id)
const row = ref(null)
const page = ref(1)
const pdf = ref(null)
const title = ref('')
const nodes = ref([])
const editing = ref(false)
const saving = ref(false)
const converting = ref(false)
const error = ref('')
const message = ref('')
const pageText = ref('')
const needsWordPreview = computed(() => ['doc', 'docx'].includes(row.value?.extension) && !row.value?.has_preview)

async function getText() {
  pageText.value = ''
  if (!row.value?.has_text || row.value.has_preview || needsWordPreview.value) return
  const number = page.value
  try {
    const content = await api(`/resources/${id}/pages/${number}`)
    if (number === page.value) pageText.value = content.text
  } catch (failure) { error.value = failure.message }
}
watch(page, getText)

function jump(number) {
  if (pdf.value && number === page.value) pdf.value.jump(number)
  else page.value = number
}

onMounted(async () => {
  try {
    row.value = await api(`/resources/${id}`)
    title.value = row.value.title
    nodes.value = row.value.outline
    if (needsWordPreview.value) await convertWord()
    else await getText()
  } catch (failure) { error.value = failure.message }
})

async function convertWord() {
  if (converting.value) return
  converting.value = true
  error.value = ''
  try {
    row.value = await api(`/resources/${id}/process`, { method: 'POST' })
    nodes.value = row.value.outline
    page.value = 1
    message.value = nodes.value.length
      ? '已生成 PDF 预览，请校对目录。'
      : '已生成 PDF 预览。未找到目录，可以手动添加章节。'
  } catch (failure) { error.value = failure.message }
  finally { converting.value = false }
}

async function save(event) {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const status = event.submitter?.value === 'ready' ? 'ready' : undefined
    row.value = await api(`/resources/${id}`, { method: 'PATCH', body: { title: title.value, outline: nodes.value, status } })
    nodes.value = row.value.outline
    editing.value = false
    message.value = status === 'ready' ? '已入库，可以在教案中选择这份资料。' : '资料信息已保存。'
  } catch (failure) { error.value = failure.message }
  finally { saving.value = false }
}

async function original() {
  try { await download(`/resources/${id}/file`, row.value.filename) }
  catch (failure) { error.value = failure.message }
}
</script>

<template>
  <div class="page">
    <RouterLink class="text-link back-link" to="/resources"><ArrowLeft :size="16" /> 返回资料库</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>
    <template v-if="row">
      <header class="page-heading"><div><h1>{{ row.title }}</h1><p>{{ row.extension.toUpperCase() }} · {{ formatSize(row.size) }}<template v-if="row.page_count"> · {{ row.page_count }} 页</template></p></div><button class="button secondary" @click="original"><Download :size="17" /> 下载原文件</button></header>
      <div class="document-layout">
        <form class="panel outline-panel stack" @submit.prevent="save">
          <label>资料名称<input v-model.trim="title" required maxlength="160"></label>
          <div class="section-heading"><h2 id="resource-outline-heading">章节目录</h2><button v-if="row.page_count" type="button" class="button subtle" @click="editing = !editing">{{ editing ? '收起编辑' : '校对目录' }}</button></div>
          <p v-if="!nodes.length" class="muted">{{ needsWordPreview ? '转换为 PDF 后可校对目录。' : '暂无目录。可以手动添加章节。' }}</p>
          <div v-else class="resource-outline-scroll" role="region" aria-labelledby="resource-outline-heading" tabindex="0">
            <ResourceOutline :nodes="nodes" :editing="editing" :max="row.page_count" @jump="jump" />
          </div>
          <button v-if="editing" class="button secondary" type="button" @click="nodes.push({ title: '', start: nodes.at(-1)?.end || 1, end: row.page_count, children: [] })"><Plus :size="16" /> 添加章节</button>
          <button class="button secondary" type="submit" :disabled="saving || converting"><Save :size="16" /> 保存资料</button>
          <button v-if="row.status !== 'ready' && row.has_text && !needsWordPreview" class="button primary" type="submit" value="ready" :disabled="saving">确认并入库</button>
          <p v-if="!row.has_text && !needsWordPreview" class="muted">没有可用正文。扫描页需要带文本层的文件。</p>
        </form>
        <PdfViewer v-if="row.has_preview" ref="pdf" :src="`/api/resources/${id}/preview`" v-model:page="page" />
        <div v-else-if="needsWordPreview" class="panel text-preview stack">
          <div class="section-heading"><h2><FileText :size="18" /> PDF 预览</h2></div>
          <p v-if="converting" class="muted" role="status">正在将原始 Word 文件转换为 PDF…</p>
          <button v-else class="button secondary" type="button" @click="convertWord">重新转换 PDF</button>
        </div>
        <div v-else class="panel text-preview">
          <header class="section-heading"><h2>提取文本</h2><input v-if="row.page_count > 1" v-model.number="page" type="number" aria-label="文本页码" min="1" :max="row.page_count"></header>
          <p class="muted">PDF 版式预览需要服务器配置 LibreOffice。</p>
          <pre>{{ pageText || '当前文件没有可显示的正文。' }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>
