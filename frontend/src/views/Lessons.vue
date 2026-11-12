<script setup>
import { computed, onMounted, ref } from 'vue'
import { Archive, BookOpen, Ellipsis, Plus, Search, Sparkles, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { api, formatDate } from '../api'
import { courseId } from '../session'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'

const route = useRoute()
const router = useRouter()
const lessons = ref([])
const resources = ref([])
const query = ref('')
const status = ref('draft')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const createOpen = ref(route.query.create === '1')
const manage = ref(null)
const newTitle = ref('')
const instruction = ref('')
const sources = ref([])
const found = computed(() => lessons.value.filter((row) => row.status === status.value && row.title.toLowerCase().includes(query.value.trim().toLowerCase())))

async function load() {
  try {
    const [plans, documents] = await Promise.all([
      api(`/lessons?course_id=${courseId.value}`), api(`/resources?course_id=${courseId.value}`),
    ])
    lessons.value = plans
    resources.value = documents.filter((row) => row.status === 'ready'
      && (!['doc', 'docx'].includes(row.extension) || row.has_preview))
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
}
onMounted(load)

function closeCreate() {
  if (busy.value) return
  createOpen.value = false
  formError.value = ''
  if (route.query.create) router.replace('/lessons')
}

function flatten(nodes, depth = 0) {
  return nodes.flatMap((node) => [{ ...node, depth }, ...flatten(node.children, depth + 1)])
}

async function chooseResource(entry) {
  entry.outline = []
  entry.start = 1
  entry.end = 1
  entry.max = 1
  if (!entry.resource_id) return
  const id = entry.resource_id
  try {
    const document = await api(`/resources/${id}`)
    if (entry.resource_id !== id) return
    entry.max = document.page_count || 1
    entry.end = entry.max
    entry.outline = flatten(document.outline)
  } catch (failure) { formError.value = failure.message }
}

function chooseSection(entry, value) {
  const node = value === '' ? null : entry.outline[Number(value)]
  entry.start = node?.start || 1
  entry.end = node?.end || entry.max
}

async function create(event) {
  if (busy.value) return
  busy.value = true
  formError.value = ''
  try {
    const generate = event.submitter?.value === 'generate'
    const body = {
      course_id: courseId.value, title: newTitle.value, instruction: instruction.value,
      sources: sources.value.filter((item) => item.resource_id).map(({ resource_id, start, end }) => ({ resource_id, start, end })),
    }
    const plan = await api(generate ? '/ai/lessons' : '/lessons', { method: 'POST', body })
    await router.push(`/lessons/${plan.id}`)
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}

async function perform(item, action, title) {
  error.value = ''
  try {
    const path = `/lessons/${item.id}`
    if (action === 'delete') await api(path, { method: 'DELETE' })
    else if (action === 'copy') await api(`${path}/copy`, { method: 'POST' })
    else {
      const details = await api(path)
      if (title) details.title = title
      else details.status = item.status === 'draft' ? 'archived' : 'draft'
      await api(path, { method: 'PUT', body: details })
    }
    manage.value = null
    await load()
  } catch (failure) { error.value = failure.message; manage.value = null }
}
</script>

<template>
  <div class="page">
    <header class="page-heading"><div><h1>教案管理</h1><p>打开、编辑和管理当前课程的教案。</p></div><button class="button primary" @click="createOpen = true"><Plus :size="18" /> 新建教案</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="list-tools">
      <div class="segmented" aria-label="教案状态"><button :aria-pressed="status === 'draft'" @click="status = 'draft'">全部教案</button><button :aria-pressed="status === 'archived'" @click="status = 'archived'"><Archive :size="15" /> 已归档</button></div>
      <label class="search"><Search :size="17" /><input v-model="query" type="search" aria-label="搜索教案" placeholder="搜索教案"></label>
    </div>
    <div v-if="loading" class="empty-state" role="status">正在加载教案</div>
    <div v-else-if="found.length" class="table-scroll">
      <table class="data-table"><thead><tr><th>教案名称</th><th>状态</th><th>版本</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody><tr v-for="item in found" :key="item.id">
          <td><RouterLink class="file-title" :to="`/lessons/${item.id}`"><span class="file-icon lesson-icon"><BookOpen :size="18" /></span><strong>{{ item.title }}</strong></RouterLink></td>
          <td><span class="status-tag">{{ item.status === 'draft' ? '草稿' : '已归档' }}</span></td><td>v{{ item.revision }}</td><td>{{ formatDate(item.updated_at) }}</td>
          <td><details class="row-menu"><summary aria-label="教案操作"><Ellipsis :size="19" /></summary><div>
            <button @click="manage = { action: 'rename', item, title: item.title }">重命名</button><button @click="perform(item, 'copy')">复制</button>
            <button @click="perform(item, 'archive')">{{ item.status === 'draft' ? '归档' : '恢复' }}</button>
            <button class="danger-text" @click="manage = { action: 'delete', item }">删除</button>
          </div></details></td>
        </tr></tbody>
      </table>
    </div>
    <Empty v-else :title="query ? '没有找到匹配的教案' : status === 'archived' ? '暂无归档教案' : '还没有教案'" :detail="!query && status === 'draft' ? '可以从空白开始，也可以选择资料用 AI 生成草稿。' : ''">
      <button v-if="!query && status === 'draft'" class="button secondary" @click="createOpen = true"><Plus :size="16" /> 新建教案</button>
    </Empty>
    <Modal :open="createOpen" title="新建教案" wide @close="closeCreate">
      <form class="stack" @submit.prevent="create">
        <label>教案名称<input v-model.trim="newTitle" required maxlength="160" placeholder="例如：函数的定义与调用"></label>
        <label>生成要求<textarea v-model="instruction" maxlength="3000" rows="3" placeholder="可填写授课对象、课时及教学目标"></textarea></label>
        <div class="section-heading"><h3>参考资料</h3><button class="button secondary" type="button" :disabled="!resources.length || sources.length >= 12" @click="sources.push({ resource_id: '', start: 1, end: 1, max: 1, outline: [] })"><Plus :size="15" /> 添加资料</button></div>
        <p v-if="!resources.length" class="muted">资料库有已入库的文件后，可选择章节或页码。</p>
        <div v-for="(entry, index) in sources" :key="index" class="source-picker">
          <label>资料<select v-model="entry.resource_id" required @change="chooseResource(entry)"><option value="">选择资料</option><option v-for="item in resources" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
          <label v-if="entry.outline.length">章节<select @change="chooseSection(entry, $event.target.value)"><option value="">全部</option><option v-for="(node, number) in entry.outline" :key="number" :value="number">{{ '　'.repeat(node.depth) }}{{ node.title }}</option></select></label>
          <div class="actions"><label>开始页<input v-model.number="entry.start" type="number" min="1" :max="entry.max" required></label><label>结束页<input v-model.number="entry.end" type="number" :min="entry.start" :max="entry.max" required></label><button class="button subtle icon-only" type="button" aria-label="移除资料" @click="sources.splice(index, 1)"><X :size="17" /></button></div>
        </div>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions"><button class="button secondary" type="submit" value="blank" :disabled="busy">创建空白教案</button><button class="button primary" type="submit" value="generate" :disabled="busy"><Sparkles :size="16" /> {{ busy ? '正在处理' : 'AI 生成教案' }}</button></div>
      </form>
    </Modal>
    <Modal :open="!!manage" :title="manage?.action === 'rename' ? '重命名教案' : '删除教案'" @close="manage = null">
      <form class="stack" @submit.prevent="perform(manage.item, manage.action, manage.title)">
        <label v-if="manage?.action === 'rename'">教案名称<input v-model.trim="manage.title" required maxlength="160"></label>
        <p v-else>删除「{{ manage?.item.title }}」？</p>
        <div class="dialog-actions"><button type="button" class="button secondary" @click="manage = null">取消</button><button type="submit" class="button" :class="manage?.action === 'rename' ? 'primary' : 'danger'">{{ manage?.action === 'rename' ? '保存' : '删除教案' }}</button></div>
      </form>
    </Modal>
  </div>
</template>
