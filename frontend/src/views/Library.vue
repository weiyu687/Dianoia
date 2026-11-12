<script setup>
import { computed, ref, onMounted } from 'vue'
import { ArrowUpRight, CloudUpload, Ellipsis, Search, Upload } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { api, download, formatDate, formatSize } from '../api'
import { courseId } from '../session'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'

const route = useRoute()
const router = useRouter()
const rows = ref([])
const query = ref('')
const loading = ref(true)
const uploading = ref(false)
const error = ref('')
const modalError = ref('')
const uploadOpen = ref(route.query.upload === '1')
const deleteTarget = ref(null)
const file = ref(null)
const title = ref('')
const dragging = ref(false)
const items = computed(() => rows.value.filter((row) => `${row.title} ${row.filename}`.toLowerCase().includes(query.value.trim().toLowerCase())))

async function load() {
  try { rows.value = await api(`/resources?course_id=${courseId.value}`) }
  catch (failure) { error.value = failure.message }
  finally { loading.value = false }
}
onMounted(load)

function pick(value) {
  if (!value) return
  modalError.value = ''
  if (!/\.(docx?|pdf|pptx)$/i.test(value.name) || value.size > 25 * 1024 * 1024) {
    modalError.value = '请选择不超过 25 MB 的 DOC、DOCX、PDF 或 PPTX。'
    return
  }
  file.value = value
  title.value = value.name.replace(/\.[^.]+$/, '').slice(0, 160)
}

async function upload() {
  if (!file.value || uploading.value) return
  uploading.value = true
  modalError.value = ''
  try {
    const body = new FormData()
    body.append('file', file.value)
    body.append('course_id', courseId.value)
    body.append('title', title.value)
    const item = await api('/resources', { method: 'POST', body })
    await router.push(`/resources/${item.id}`)
  } catch (failure) { modalError.value = failure.message }
  finally { uploading.value = false }
}

function closeUpload() {
  if (uploading.value) return
  uploadOpen.value = false
  file.value = null
  modalError.value = ''
  if (route.query.upload) router.replace('/resources')
}

async function remove() {
  try {
    await api(`/resources/${deleteTarget.value.id}`, { method: 'DELETE' })
    rows.value = rows.value.filter((item) => item.id !== deleteTarget.value.id)
    deleteTarget.value = null
  } catch (failure) { error.value = failure.message; deleteTarget.value = null }
}

async function original(item) {
  try { await download(`/resources/${item.id}/file`, item.filename) }
  catch (failure) { error.value = failure.message }
}
</script>

<template>
  <div class="page">
    <header class="page-heading"><div><h1>资料库</h1><p>上传、预览和管理当前课程的教学资料。</p></div><button class="button primary" @click="uploadOpen = true"><Upload :size="17" /> 上传资料</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="list-tools"><label class="search"><Search :size="17" /><input v-model="query" type="search" aria-label="搜索资料" placeholder="搜索资料"></label><span class="muted">{{ rows.length }} 份资料</span></div>
    <div v-if="loading" class="empty-state" role="status">正在加载资料</div>
    <div v-else-if="items.length" class="table-scroll">
      <table class="data-table"><thead><tr><th>资料名称</th><th>大小</th><th>状态</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody><tr v-for="item in items" :key="item.id">
          <td><RouterLink class="file-title" :to="`/resources/${item.id}`"><span class="file-icon" :data-type="item.extension">{{ item.extension.toUpperCase() }}</span><span><strong>{{ item.title }}</strong><small>{{ item.filename }}</small></span></RouterLink></td>
          <td>{{ formatSize(item.size) }}</td><td><span class="status-tag" :class="{ ready: item.status === 'ready' }">{{ item.status === 'ready' ? '已入库' : '待校对' }}</span></td>
          <td>{{ formatDate(item.updated_at) }}</td>
          <td><details class="row-menu"><summary aria-label="资料操作"><Ellipsis :size="19" /></summary><div><RouterLink :to="`/resources/${item.id}`">预览与编辑 <ArrowUpRight :size="14" /></RouterLink><button @click="original(item)">下载原文件</button><button class="danger-text" @click="deleteTarget = item">删除</button></div></details></td>
        </tr></tbody>
      </table>
    </div>
    <Empty v-else :title="query ? '没有找到匹配的资料' : '资料库还是空的'" :detail="query ? '' : '上传讲义、课件或教材，随后预览并校对目录。'">
      <button v-if="!query" class="button secondary" @click="uploadOpen = true"><Upload :size="16" /> 上传资料</button>
    </Empty>
    <Modal :open="uploadOpen" title="上传资料" @close="closeUpload">
      <form class="stack" @submit.prevent="upload">
        <label class="dropzone" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dragging = false; pick($event.dataTransfer.files[0])">
          <CloudUpload :size="28" /><strong>{{ file?.name || '选择文件或拖拽到这里' }}</strong><small>DOC、DOCX、PDF、PPTX · 单个文件 25 MB 以内</small>
          <input type="file" accept=".doc,.docx,.pdf,.pptx" aria-label="选择资料文件" @change="pick($event.target.files[0])">
        </label>
        <label>资料名称<input v-model.trim="title" placeholder="可使用文件名" maxlength="160"></label>
        <p v-if="modalError" class="error" role="alert">{{ modalError }}</p>
        <div class="dialog-actions"><button class="button secondary" type="button" @click="closeUpload" :disabled="uploading">取消</button><button class="button primary" type="submit" :disabled="!file || uploading">{{ uploading ? '正在上传并解析' : '上传并预览' }}</button></div>
      </form>
    </Modal>
    <Modal :open="!!deleteTarget" title="删除资料" @close="deleteTarget = null">
      <p>删除「{{ deleteTarget?.title }}」及其原文件？</p>
      <div class="dialog-actions"><button class="button secondary" @click="deleteTarget = null">取消</button><button class="button danger" @click="remove">删除资料</button></div>
    </Modal>
  </div>
</template>
