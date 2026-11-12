<script setup>
import { onMounted, ref, watch } from 'vue'
import { ArrowLeft, Download, Plus, Save } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { api, download, formatSize } from '../api'
import ResourceOutline from '../components/ResourceOutline.vue'
import PdfViewer from '../components/PdfViewer.vue'

const id = String(useRoute().params.id)
const row = ref(null)
const page = ref(1)
const title = ref('')
const nodes = ref([])
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const pageText = ref('')

async function getText() {
  pageText.value = ''
  if (!row.value?.has_text || row.value.has_preview) return
  const number = page.value
  try {
    const content = await api(`/resources/${id}/pages/${number}`)
    if (number === page.value) pageText.value = content.text
  } catch (failure) { error.value = failure.message }
}
watch(page, getText)

onMounted(async () => {
  try {
    row.value = await api(`/resources/${id}`)
    title.value = row.value.title
    nodes.value = row.value.outline
    await getText()
  } catch (failure) { error.value = failure.message }
})

async function save(event) {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const status = event.submitter?.value === 'ready' ? 'ready' : row.value.status
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
          <div class="section-heading"><h2>章节目录</h2><button v-if="row.page_count" type="button" class="button subtle" @click="editing = !editing">{{ editing ? '收起编辑' : '校对目录' }}</button></div>
          <p v-if="!nodes.length" class="muted">暂无目录。可以手动添加章节。</p>
          <ResourceOutline :nodes="nodes" :editing="editing" :max="row.page_count" @jump="page = $event" />
          <button v-if="editing" class="button secondary" type="button" @click="nodes.push({ title: '', start: nodes.at(-1)?.end || 1, end: row.page_count, children: [] })"><Plus :size="16" /> 添加章节</button>
          <button class="button secondary" type="submit" :disabled="saving"><Save :size="16" /> 保存资料</button>
          <button v-if="row.status !== 'ready' && row.has_text" class="button primary" type="submit" value="ready" :disabled="saving">确认并入库</button>
          <p v-if="!row.has_text" class="muted">没有可用正文。扫描页需要带文本层的文件。</p>
        </form>
        <PdfViewer v-if="row.has_preview" :src="`/api/resources/${id}/preview`" v-model:page="page" />
        <div v-else class="panel text-preview">
          <header class="section-heading"><h2>提取文本</h2><input v-if="row.page_count > 1" v-model.number="page" type="number" aria-label="文本页码" min="1" :max="row.page_count"></header>
          <p class="muted">PDF 版式预览需要服务器配置 LibreOffice。</p>
          <pre>{{ pageText || '当前文件没有可显示的正文。' }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>
