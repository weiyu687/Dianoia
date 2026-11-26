<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronLeft, ChevronRight, Download, Film, Headphones, Mic, Save, Sparkles, Trash2, UserRound } from 'lucide-vue-next'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import '../digitalCourses.css'

const workspace = '/digital-courses'
const router = useRouter()
const path = workspace + '/' + useRoute().params.id
const project = ref(null)
const assets = ref([])
const folders = ref([])
const studioPresets = ref({ themes: {}, layouts: {} })
const materialKind = ref('avatar')
const materialSource = ref('official')
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
const anyScript = computed(() => project.value?.slides.some((page) => page.script.trim()))
const readable = (page) => Boolean(page?.text?.trim() || page?.notes?.trim())
const readablePages = computed(() => project.value?.slides.some(readable))
const missingPages = computed(() => project.value?.slides.some((page) => readable(page) && !page.script.trim()))
const chosenAvatar = computed(() => assets.value.find((asset) => asset.id === project.value?.avatar))
const selectedTheme = computed(() => studioPresets.value.themes[project.value?.studio?.theme])
const pageScene = computed(() => project.value?.studio?.pages[index.value] || 'auto')
function sceneKey(i) {
  const studio = project.value.studio
  const override = studio.pages[i]
  if (override && override !== 'auto') return override
  if (studio.layout !== 'auto') return studio.layout
  return i === 0 || i === project.value.page_count - 1 ? 'studio' : 'focus'
}
const scene = computed(() => project.value && studioPresets.value.layouts[sceneKey(index.value)])
const hasPresenterScenes = computed(() => project.value?.slides.some((_, i) => sceneKey(i) !== 'focus'))
const sceneStyle = computed(() => {
  const theme = selectedTheme.value
  if (!theme) return {}
  return {
    '--stage-top': theme.top, '--stage-bottom': theme.bottom,
    '--stage-ink': theme.ink, '--stage-accent': theme.accent,
    '--stage-frame': theme.frame, '--stage-matte': theme.matte,
  }
})
function placement(bounds) {
  const [x, y, width, height] = bounds
  return { left: `${x / 19.2}%`, top: `${y / 10.8}%`, width: `${width / 19.2}%`, height: `${height / 10.8}%` }
}
function chooseScene(value) {
  project.value.studio.pages = Array.from({ length: project.value.page_count }, (_, i) =>
    i === index.value ? value : project.value.studio.pages[i] || 'auto')
  changed.value = true
}
const options = computed(() => {
  const grouped = new Set(folders.value.flatMap((folder) => folder.samples.map((sample) => sample.id)))
  return [
    ...assets.value.filter((asset) => !grouped.has(asset.id) || asset.id === project.value?.voice),
    ...folders.value.map((folder) => ({
      id: 'folder-' + folder.id, kind: 'voice', name: folder.name, preset: false, count: folder.samples.length,
      previewId: folder.reference_id, unavailable: !folder.reference_id,
    })),
  ]
})
const chosenVoice = computed(() => options.value.find((asset) => asset.id === project.value?.voice && !asset.unavailable))
const visibleMaterials = computed(() => options.value.filter((asset) => asset.kind === materialKind.value &&
  asset.preset === (materialSource.value === 'official')))
const video = '/api' + path + '/video'
const audio = '/api' + path + '/audio'
const videoPreview = '/api' + path + '/preview-video'
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
    const [data, catalog, voiceFolders, presets] = await Promise.all([
      api(path), api(workspace + '/assets'), api(workspace + '/voice-folders'), api(workspace + '/studio-presets'),
    ])
    if (disposed) return
    assets.value = catalog
    folders.value = voiceFolders
    studioPresets.value = presets
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
  const { title, avatar, voice, revision, slides, studio } = project.value
  const value = await api(path, {
    method: 'PUT', body: { title, avatar, voice, revision, studio, scripts: slides.map((page) => page.script) },
  })
  changed.value = false
  receive(value)
}

function chooseMaterial(item) {
  if (locked.value || item.unavailable || project.value[item.kind] === item.id) return
  project.value[item.kind] = item.id
  changed.value = true
}

async function act(kind, scope) {
  if (locked.value) return
  if (kind === 'scripts' && scope === 'page' && slide.value.script.trim() && !window.confirm('用新稿件替换本页现有口播稿？')) return
  if (kind === 'scripts' && scope === 'all' && anyScript.value &&
      !window.confirm('为所有有可读内容的页面重新生成讲稿，并替换这些页面的现有稿件？')) return
  const page = scope === 'page' ? index.value + 1 : undefined
  busy.value = true
  error.value = ''
  try {
    await save()
    if (kind !== 'save') receive(await api(path + '/jobs', { method: 'POST',
      body: { kind, revision: project.value.revision, page, replace_existing: scope === 'all' } }))
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
          <button class="button secondary" :disabled="locked || !readablePages" @click="act('scripts', 'all')"><Sparkles :size="16" /> 一键生成全部讲稿</button>
          <button class="button subtle icon-only danger-text" title="删除项目" aria-label="删除项目" :disabled="locked" @click="deleting = true"><Trash2 :size="16" /></button>
          <button class="button secondary" :disabled="locked || !changed" @click="act('save')"><Save :size="16" /> 保存</button>
          <button class="button primary" :disabled="locked || !isComplete || (hasPresenterScenes && !chosenAvatar) || !chosenVoice" @click="act('video')"><Film :size="17" /> 生产视频</button>
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
        <div class="digital-center">
          <section class="digital-preview" aria-label="课件预览">
            <div class="digital-stage-bar"><strong>画面预览</strong><small>{{ scene?.name }} · 16:9 · 1080p</small></div>
            <div v-if="scene" class="digital-slide-frame" :style="sceneStyle">
              <div class="digital-stage-caption"><span>{{ project.title }}</span><span>{{ String(index + 1).padStart(2, '0') }} / {{ String(project.page_count).padStart(2, '0') }}</span></div>
              <div class="digital-stage-deck" :style="placement(scene.slide)">
                <img :src="slideImage(index)" :alt="'第 ' + (index + 1) + ' 页课件预览'">
              </div>
              <div v-if="scene.avatar" class="digital-stage-avatar" :style="placement(scene.avatar)">
                <img v-if="chosenAvatar" :src="preview(chosenAvatar.id)" :alt="chosenAvatar.name">
                <button v-else class="button subtle" @click="materialKind = 'avatar'"><UserRound :size="18" /> 选择讲师</button>
              </div>
            </div>
            <div class="digital-scene-controls">
              <label>背景主题<select v-model="project.studio.theme" :disabled="locked" @change="changed = true">
                <option v-for="(theme, key) in studioPresets.themes" :key="key" :value="key">{{ theme.name }}</option>
              </select></label>
              <label>整课分镜<select v-model="project.studio.layout" :disabled="locked" @change="changed = true">
                <option value="auto">自动分镜</option>
                <option v-for="(item, key) in studioPresets.layouts" :key="key" :value="key">{{ item.name }}</option>
              </select></label>
              <label>本页构图<select :value="pageScene" :disabled="locked" @change="chooseScene($event.target.value)">
                <option value="auto">继承整课设置</option>
                <option v-for="(item, key) in studioPresets.layouts" :key="key" :value="key">{{ item.name }}</option>
              </select></label>
            </div>
            <p v-if="sceneKey(index) === 'pip'" class="muted">讲师画面覆盖课件右下角，可在预览中检查是否挡住内容。</p>
            <div class="digital-page-nav">
              <button class="button subtle icon-only" aria-label="上一页" :disabled="!index" @click="index--"><ChevronLeft :size="18" /></button>
              <span>{{ index + 1 }} / {{ project.page_count }}</span>
              <button class="button subtle icon-only" aria-label="下一页" :disabled="index + 1 === project.page_count" @click="index++"><ChevronRight :size="18" /></button>
            </div>
          </section>
          <section class="digital-script">
            <div class="section-heading"><h2>第 {{ index + 1 }} 页口播稿</h2><small>{{ slide.script.length }} / 1500 字</small></div>
            <div class="actions">
              <button class="button secondary" :disabled="locked || !slide.script.trim() || !chosenVoice" @click="act('audio', 'page')"><Headphones :size="16" /> 试听本页讲稿</button>
              <button class="button secondary" :disabled="locked || !slide.script.trim() || !chosenVoice || (scene?.avatar && !chosenAvatar)"
                title="生成本页开头最多 12 秒的成片" @click="act('preview', 'page')"><Film :size="16" /> 试看本页</button>
              <button class="button subtle" :disabled="locked || !readable(slide)" @click="act('scripts', 'page')"><Sparkles :size="15" /> AI 生成本页</button>
              <button class="button subtle" :disabled="locked || !missingPages" @click="act('scripts')">补齐空白页</button>
            </div>
            <audio v-if="project.audio_available && !changed && job.page === index + 1" :key="job.id" :src="audio" controls aria-label="播放本页合成讲稿" />
            <video v-if="project.preview_available && !changed && job.page === index + 1"
              class="digital-short-preview" :key="job.id" :src="videoPreview" controls playsinline preload="metadata" aria-label="本页成片试看片段" />
            <textarea v-model="slide.script" :disabled="locked" maxlength="1500" rows="7" aria-label="本页口播稿"
              placeholder="输入讲稿，或用本页课件和讲者备注生成初稿。" @input="changed = true" />
            <p v-if="!readable(slide)" class="muted">本页无可读文字，可以查看预览后手动撰写。</p>
            <details v-if="slide.notes"><summary>原课件讲者备注</summary><p>{{ slide.notes }}</p></details>
          </section>
        </div>
        <aside class="digital-materials" aria-label="讲师形象与声音">
          <nav class="digital-material-kind" aria-label="素材类型">
            <button class="button" :class="materialKind === 'avatar' ? 'secondary' : 'subtle'" :aria-pressed="materialKind === 'avatar'" @click="materialKind = 'avatar'"><UserRound :size="17" /> 形象</button>
            <button class="button" :class="materialKind === 'voice' ? 'secondary' : 'subtle'" :aria-pressed="materialKind === 'voice'" @click="materialKind = 'voice'"><Mic :size="17" /> 声音</button>
          </nav>
          <nav class="digital-material-source" aria-label="素材来源">
            <button class="button subtle" :aria-pressed="materialSource === 'official'" @click="materialSource = 'official'">官方素材</button>
            <button class="button subtle" :aria-pressed="materialSource === 'mine'" @click="materialSource = 'mine'">我的素材</button>
            <RouterLink class="text-link" :to="{ path: workspace, query: { tab: materialKind, source: materialSource } }">管理</RouterLink>
          </nav>
          <p v-if="chosenAvatar || chosenVoice" class="digital-selection">
            {{ materialKind === 'avatar' ? (chosenAvatar?.name || '请选择形象') : (chosenVoice?.name || '请选择声音') }}
          </p>
          <div :class="materialKind === 'avatar' ? 'digital-avatar-grid' : 'digital-voice-options'">
            <article v-for="asset in visibleMaterials" :key="asset.id" :class="{ 'digital-material-active': project[asset.kind] === asset.id }">
              <button class="digital-material-pick" :aria-pressed="project[asset.kind] === asset.id" :disabled="locked || asset.unavailable"
                @click="chooseMaterial(asset)">
                <img v-if="asset.kind === 'avatar'" :src="preview(asset.id)" alt="">
                <span>{{ asset.name }}</span><small v-if="asset.count != null">{{ asset.unavailable ? '待指定参考样本' : asset.count + ' 条样本' }}</small>
              </button>
              <audio v-if="asset.kind === 'voice' && !asset.unavailable" :src="preview(asset.previewId || asset.id)"
                controls :preload="asset.preset ? 'metadata' : 'none'" :aria-label="'试听 ' + asset.name" />
            </article>
          </div>
          <p v-if="!visibleMaterials.length" class="muted">此分类暂无素材。</p>
        </aside>
      </div>
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
