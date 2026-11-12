<script setup>
import { onMounted, ref } from 'vue'
import { ArrowLeft, Eye, FileText, Pencil, Trash2, Upload } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'
import PdfViewer from '../components/PdfViewer.vue'

const templates = ref([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const action = ref('')
const current = ref(null)
const title = ref('')
const file = ref(null)
const page = ref(1)

onMounted(async () => {
  try { templates.value = await api('/lesson-templates') }
  catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function open(next, template = null) {
  current.value = template
  title.value = template?.title || ''
  file.value = null
  page.value = 1
  formError.value = ''
  action.value = next
}

function selectFile(event) {
  const selected = event.target.files[0]
  if (!selected) return
  if (!/\.docx?$/i.test(selected.name) || selected.size > 25 * 1024 * 1024) {
    file.value = null
    formError.value = '请选择不超过 25 MB 的 DOC 或 DOCX 文件'
    return
  }
  file.value = selected
  title.value = selected.name.replace(/\.[^.]+$/, '').slice(0, 160)
  formError.value = ''
}

async function submit() {
  if (busy.value) return
  busy.value = true
  formError.value = ''
  try {
    if (action.value === 'upload') {
      const body = new FormData()
      body.append('file', file.value)
      body.append('title', title.value)
      templates.value.unshift(await api('/lesson-templates', { method: 'POST', body }))
    } else if (action.value === 'rename') {
      const template = await api(`/lesson-templates/${current.value.id}`, {
        method: 'PATCH', body: { title: title.value },
      })
      templates.value = templates.value.map((item) => item.id === template.id ? template : item)
    } else {
      await api(`/lesson-templates/${current.value.id}`, { method: 'DELETE' })
      templates.value = templates.value.filter((item) => item.id !== current.value.id)
    }
    action.value = ''
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}

const labels = { upload: '上传 Word 模板', rename: '重命名模板', remove: '删除模板' }
</script>

<template>
  <div class="page">
    <RouterLink class="text-link back-link" to="/lessons"><ArrowLeft :size="16" /> 返回教案管理</RouterLink>
    <header class="page-heading"><div><h1>Word 模板</h1><p>管理可在新教案中复用的 Word 文档。</p></div>
      <button class="button primary" @click="open('upload')"><Upload :size="17" /> 上传模板</button>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading" class="empty-state" role="status">正在加载模板</div>
    <div v-else-if="templates.length" class="table-scroll">
      <table class="data-table"><thead><tr><th>模板名称</th><th>上传时间</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody><tr v-for="template in templates" :key="template.id">
          <td><button class="outline-link file-title" type="button" @click="open('preview', template)">
            <span class="file-icon"><FileText :size="19" /></span>
            <span><strong>{{ template.title }}</strong><small>{{ template.filename }}</small></span>
          </button></td>
          <td>{{ formatDate(template.created_at) }}</td>
          <td><div class="actions template-actions">
            <button class="button subtle icon-only" type="button" :aria-label="`预览 ${template.title}`" @click="open('preview', template)"><Eye :size="17" /></button>
            <button class="button subtle icon-only" type="button" :aria-label="`重命名 ${template.title}`" @click="open('rename', template)"><Pencil :size="17" /></button>
            <button class="button subtle icon-only danger-text" type="button" :aria-label="`删除 ${template.title}`" @click="open('remove', template)"><Trash2 :size="17" /></button>
          </div></td>
        </tr></tbody>
      </table>
    </div>
    <Empty v-else title="还没有 Word 模板" detail="上传学校的 DOC 或 DOCX，之后可在新建教案时选择。" />
    <Modal :open="action === 'preview'" :title="current?.title || '模板预览'" wide @close="action = ''">
      <PdfViewer v-if="current" :src="`/api/lesson-templates/${current.id}/preview`" v-model:page="page" />
    </Modal>
    <Modal :open="!!labels[action]" :title="labels[action]" @close="!busy && (action = '')">
      <form class="stack" @submit.prevent="submit">
        <label v-if="action === 'upload'">Word 文件<input type="file" aria-label="选择 Word 模板" accept=".doc,.docx" required @change="selectFile"></label>
        <label v-if="action !== 'remove'">模板名称<input v-model.trim="title" maxlength="160" required></label>
        <p v-else>删除「{{ current?.title }}」？已从该模板创建的教案仍可编辑。</p>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions">
          <button type="button" class="button secondary" :disabled="busy" @click="action = ''">取消</button>
          <button type="submit" class="button" :class="action === 'remove' ? 'danger' : 'primary'" :disabled="busy || (action === 'upload' && !file)">{{ busy ? '正在处理' : action === 'remove' ? '删除模板' : '保存模板' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
