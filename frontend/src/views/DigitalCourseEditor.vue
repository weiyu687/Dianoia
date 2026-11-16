<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronLeft, ChevronRight, Download, Film, Save, Sparkles, Trash2 } from 'lucide-vue-next'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import '../digitalCourses.css'

const workspace = '/digital-courses'
const router = useRouter()
const path = workspace + '/' + useRoute().params.id
const project = ref(null)
const assets = ref([])
const index = ref(0)
const changed = ref(false)
const busy = ref(false)
const deleting = ref(false)
const error = ref('')
const pollError = ref('')
let timer
let disposed = false

const job = computed(() => project.value?.job)
const active = computed(() => ['queued', 'running'].includes(job.value?.status))
const locked = computed(() => active.value || busy.value)
const slide = computed(() => project.value?.slides[index.value])
const isComplete = computed(() => project.value?.slides.every((page) => page.script.trim()))
const chosenAvatar = computed(() => assets.value.find((asset) => asset.id === project.value?.avatar))
const chosenVoice = computed(() => assets.value.find((asset) => asset.id === project.value?.voice))
const video = '/api' + path + '/video'
const preview = (id) => '/api' + workspace + '/assets/' + id + '/preview'
const slideImage = (i) => '/api' + path + '/pages/' + (i + 1)

function receive(value) {
  project.value = value
  clearTimeout(timer)
  if (active.value && !disposed) timer = setTimeout(refresh, 1800)
}

async function refresh() {
  try {
    const current = await api(path)
    if (disposed) return
    pollError.value = ''
    receive(current)
  } catch (failure) {
    if (disposed) return
    pollError.value = failure.message
    if (failure.status !== 401 && failure.status !== 404) timer = setTimeout(refresh, 4000)
  }
}

function leave(event) {
  if (changed.value) { event.preventDefault(); event.returnValue = '' }
}

onMounted(async () => {
  window.addEventListener('beforeunload', leave)
  try {
    const [data, catalog] = await Promise.all([api(path), api(workspace + '/assets')])
    if (disposed) return
    assets.value = catalog
    receive(data)
  } catch (failure) { error.value = failure.message }
})
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
  window.removeEventListener('beforeunload', leave)
})
onBeforeRouteLeave(() => !changed.value || window.confirm('还有未保存的修改，确定离开？'))

async function save() {
  if (!changed.value) return
  const { title, avatar, voice, revision, slides } = project.value
  const value = await api(path, { method: 'PUT', body: { title, avatar, voice, revision, scripts: slides.map((page) => page.script) } })
  changed.value = false
  receive(value)
}

async function act(kind, currentPage) {
  if (locked.value) return
  if (kind === 'scripts' && currentPage && slide.value.script.trim() && !window.confirm('用新稿件替换本页现有口播稿？')) return
  busy.value = true
  error.value = ''
  try {
    await save()
    if (kind !== 'save') receive(await api(path + '/jobs', { method: 'POST',
      body: { kind, revision: project.value.revision, ...(currentPage && { page: index.value + 1 }) } }))
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function remove() {
  busy.value = true
  error.value = ''
  try {
    await api(path + '?revision=' + project.value.revision, { method: 'DELETE' })
    changed.value = false
    await router.push(workspace)
  } catch (failure) { error.value = failure.message; deleting.value = false }
  finally { busy.value = false }
}
</script>

<template>
  <div class="page digital-courses digital-editor">
    <RouterLink class="text-link back-link" :to="workspace"><ArrowLeft :size="16" /> 数字课程</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!project && !error" class="empty-state" role="status">正在加载项目</p>
    <template v-if="project">
      <header class="page-heading">
        <div class="digital-project-title"><input v-model="project.title" aria-label="项目名称" maxlength="160" :disabled="locked" @input="changed = true">
          <p>{{ project.filename }} · {{ project.page_count }} 页<span v-if="changed"> · 有未保存的修改</span></p></div>
        <div class="actions">
          <button class="button subtle icon-only danger-text" title="删除项目" aria-label="删除项目" :disabled="locked" @click="deleting = true"><Trash2 :size="16" /></button>
          <button class="button secondary" :disabled="locked || !changed" @click="act('save')"><Save :size="16" /> 保存</button>
          <button class="button primary" :disabled="locked || !isComplete || !chosenAvatar || !chosenVoice" @click="act('video')"><Film :size="17" /> 生产视频</button>
        </div>
      </header>
      <section v-if="job" class="panel digital-job" aria-label="生产进度">
        <div role="status"><strong>{{ job.stage }}</strong><small>{{ job.completed }} / {{ job.total }} 页</small></div>
        <progress :value="job.completed" :max="job.total" aria-label="已处理页面"></progress>
        <p v-if="job.error" class="error">{{ job.error }}</p>
        <p v-if="pollError" class="error">{{ pollError }} <button class="button subtle" @click="refresh">重新查询</button></p>
      </section>
      <div class="digital-workspace panel">
        <aside class="digital-pages" aria-label="课件页面">
          <button v-for="(page, i) in project.slides" :key="i" type="button" class="digital-page"
            :aria-pressed="index === i" :aria-label="'打开第 ' + (i + 1) + ' 页'" @click="index = i">
            <img :src="slideImage(i)" alt="" loading="lazy"><span><b>{{ i + 1 }}</b> {{ page.title }}</span>
            <small :class="{ 'digital-done': page.script.trim() }">{{ page.script.trim() ? '已填写' : '待撰写' }}</small>
          </button>
        </aside>
        <section class="digital-preview" aria-label="课件预览">
          <div class="digital-slide-frame"><img :src="slideImage(index)" :alt="'第 ' + (index + 1) + ' 页课件预览'"></div>
          <div class="digital-page-nav">
            <button class="button subtle icon-only" aria-label="上一页" :disabled="!index" @click="index--"><ChevronLeft :size="18" /></button>
            <span>{{ index + 1 }} / {{ project.page_count }}</span>
            <button class="button subtle icon-only" aria-label="下一页" :disabled="index + 1 === project.page_count" @click="index++"><ChevronRight :size="18" /></button>
          </div>
        </section>
        <aside class="digital-script">
          <div class="section-heading"><h2>第 {{ index + 1 }} 页口播稿</h2></div>
          <textarea v-model="slide.script" :disabled="locked" maxlength="1500" rows="12" aria-label="本页口播稿"
            placeholder="输入讲稿，或用本页课件和讲者备注生成初稿。" @input="changed = true" />
          <small>{{ slide.script.length }} / 1500 字</small>
          <div class="actions">
            <button class="button secondary" :disabled="locked || !(slide.text || slide.notes)" @click="act('scripts', true)"><Sparkles :size="15" /> AI 生成本页</button>
            <button class="button subtle" :disabled="locked || isComplete" @click="act('scripts')">生成未填写页</button>
          </div>
          <p v-if="!slide.text && !slide.notes" class="muted">本页无可读文字，可以查看预览后手动撰写。</p>
          <details v-if="slide.notes"><summary>原课件讲者备注</summary><p>{{ slide.notes }}</p></details>
        </aside>
      </div>
      <section class="panel digital-casting">
        <div class="section-heading"><h2>讲师形象与音色</h2><RouterLink class="text-link" :to="{ path: workspace, query: { tab: 'avatar' } }">管理素材</RouterLink></div>
        <div class="digital-cast-options">
          <div>
            <label>形象<select v-model="project.avatar" aria-label="形象" :disabled="locked" @change="changed = true">
              <option value="">选择形象</option>
              <option v-if="project.avatar && !chosenAvatar" :value="project.avatar" disabled>原形象已不可用</option>
              <option v-for="asset in assets.filter((item) => item.kind === 'avatar')" :key="asset.id" :value="asset.id">{{ asset.name }}{{ asset.preset ? ' · 预设' : '' }}</option>
            </select></label>
            <img v-if="chosenAvatar" :src="preview(chosenAvatar.id)" :alt="chosenAvatar.name">
          </div>
          <div>
            <label>音色<select v-model="project.voice" aria-label="音色" :disabled="locked" @change="changed = true">
              <option value="">选择音色</option>
              <option v-if="project.voice && !chosenVoice" :value="project.voice" disabled>原音色已不可用</option>
              <option v-for="asset in assets.filter((item) => item.kind === 'voice')" :key="asset.id" :value="asset.id">{{ asset.name }}{{ asset.preset ? ' · 预设' : '' }}</option>
            </select></label>
            <audio v-if="chosenVoice" :key="chosenVoice.id" :src="preview(chosenVoice.id)" controls preload="none" aria-label="试听音色" />
          </div>
        </div>
      </section>
      <section v-if="project.has_video" class="panel digital-output">
        <div class="section-heading"><h2>课程视频{{ project.video_is_previous || changed ? '（上次生成）' : '' }}</h2>
          <a class="button secondary" :href="video + '?download=true'" download><Download :size="16" /> 导出 MP4</a></div>
        <video :key="project.updated_at" :src="video" controls playsinline preload="metadata" />
      </section>
    </template>
    <Modal :open="deleting" title="删除数字课程" @close="!busy && (deleting = false)">
      <p>确定删除这个项目及其生成的视频？</p>
      <div class="actions"><button class="button subtle" :disabled="busy" @click="deleting = false">取消</button>
        <button class="button primary" :disabled="busy" @click="remove">确认删除</button></div>
    </Modal>
  </div>
</template>
