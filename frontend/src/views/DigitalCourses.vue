<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight, Film, Mic, Plus, Upload, UserRound } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import Modal from '../components/Modal.vue'
import { courseId } from '../session'
import '../digitalCourses.css'

const workspace = '/digital-courses'
const router = useRouter()
const projects = ref([])
const assets = ref([])
const requestedTab = useRoute().query.tab
const tab = ref(['avatar', 'voice'].includes(requestedTab) ? requestedTab : 'projects')
const modal = ref(null)
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const formError = ref('')
const visibleAssets = computed(() => assets.value.filter((asset) => asset.kind === tab.value))
const media = (id) => '/api' + workspace + '/assets/' + id + '/preview'
const tabs = [
  { key: 'projects', label: '课程项目', icon: Film },
  { key: 'avatar', label: '形象库', icon: UserRound },
  { key: 'voice', label: '音色与样本库', icon: Mic },
]

onMounted(async () => {
  try {
    [projects.value, assets.value] = await Promise.all([api(workspace + '?course_id=' + courseId.value), api(workspace + '/assets')])
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function open(kind, asset = null) {
  modal.value = { kind, asset, name: asset?.name || '', transcript: '', consent: false }
  formError.value = ''
}

async function submit(event) {
  const current = modal.value
  busy.value = true
  formError.value = ''
  try {
    if (current.kind === 'rename' || current.kind === 'delete') {
      await api(workspace + '/assets/' + current.asset.id, {
        method: current.kind === 'delete' ? 'DELETE' : 'PATCH',
        body: current.kind === 'delete' ? undefined : { name: current.name },
      })
    } else {
      const body = new FormData(event.target)
      if (current.kind === 'projects') {
        body.set('course_id', courseId.value)
        const project = await api(workspace, { method: 'POST', body })
        await router.push(workspace + '/' + project.id)
        return
      }
      body.set('kind', current.kind)
      body.set('consent', String(current.consent))
      await api(workspace + '/assets', { method: 'POST', body })
    }
    assets.value = await api(workspace + '/assets')
    modal.value = null
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="page digital-courses">
    <header class="page-heading">
      <div><h1>数字课程</h1><p>导入课件，逐页编排讲稿，制作带数字讲师的视频。</p></div>
      <button class="button primary" @click="open(tab)"><Plus :size="17" />{{ { projects: '导入课件', avatar: '上传形象', voice: '上传声音样本' }[tab] }}</button>
    </header>
    <nav class="digital-tabs" aria-label="数字课程工作区">
      <button v-for="item in tabs" :key="item.key" class="button" :class="tab === item.key ? 'secondary' : 'subtle'"
        :aria-pressed="tab === item.key" @click="tab = item.key"><component :is="item.icon" :size="16" />{{ item.label }}</button>
    </nav>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="loading" class="empty-state" role="status">正在加载数字课程</p>
    <section v-else-if="tab === 'projects'" class="digital-projects">
      <RouterLink v-for="project in projects" :key="project.id" class="panel digital-project" :to="workspace + '/' + project.id">
        <img :src="'/api' + workspace + '/' + project.id + '/pages/1'" alt="" loading="lazy">
        <div><h3>{{ project.title }}</h3><small>{{ project.page_count }} 页 · {{ formatDate(project.updated_at) }}</small>
          <small>{{ project.job?.stage || '讲稿草稿' }}</small></div><ArrowUpRight :size="18" />
      </RouterLink>
      <div v-if="!projects.length" class="empty-state"><Film :size="28" /><h2>开始制作数字课程</h2><p>上传课程 PPT 或 PPTX。</p>
        <button class="button secondary" @click="open('projects')"><Upload :size="16" /> 导入课件</button></div>
    </section>
    <section v-else class="digital-assets">
      <article v-for="asset in visibleAssets" :key="asset.id" class="panel digital-asset">
        <img v-if="asset.kind === 'avatar'" :src="media(asset.id)" :alt="asset.name">
        <audio v-else :src="media(asset.id)" controls preload="none" :aria-label="asset.name" />
        <div><h3>{{ asset.name }}</h3><small>{{ asset.preset ? '预设' : '我的素材' }}</small></div>
        <p v-if="asset.transcript">{{ asset.transcript }}</p>
        <div v-if="!asset.preset" class="actions"><button class="button subtle" @click="open('rename', asset)">重命名</button>
          <button class="button subtle danger-text" @click="open('delete', asset)">删除</button></div>
      </article>
      <p v-if="!visibleAssets.length" class="empty-state">{{ tab === 'avatar' ? '暂无形象，上传一张正面照片开始。' : '暂无音色，可上传自己的语音样本。' }}</p>
    </section>
    <Modal :open="!!modal" :title="modal ? { projects: '导入课件', avatar: '上传形象', voice: '上传声音样本', rename: '重命名素材', delete: '删除素材' }[modal.kind] : ''"
      @close="!busy && (modal = null)">
      <form v-if="modal" class="form digital-form" @submit.prevent="submit">
        <template v-if="modal.kind === 'projects'">
          <label>PowerPoint 课件<input name="file" type="file" accept=".ppt,.pptx" required></label>
          <p class="muted">最多 40 页、50 MB。导入后可以逐页预览。</p>
        </template>
        <p v-else-if="modal.kind === 'delete'">确定删除「{{ modal.asset.name }}」？</p>
        <template v-else>
          <label>素材名称<input v-model="modal.name" name="name" required maxlength="100"></label>
          <template v-if="modal.kind !== 'rename'">
            <label>{{ modal.kind === 'avatar' ? '形象照片' : '语音样本' }}
              <input type="file" name="file" :accept="modal.kind === 'avatar' ? '.png,.jpg,.jpeg' : '.wav,.mp3'" required></label>
            <p class="muted">{{ modal.kind === 'avatar' ? 'PNG 或 JPG，建议使用背景简洁、光线均匀的单人正面照片。' : 'WAV 或 MP3，3 至 30 秒，建议使用无背景音乐的单人清晰朗读。' }}</p>
            <label v-if="modal.kind === 'voice'">样本中实际朗读的内容<textarea v-model="modal.transcript" name="transcript" rows="3" required maxlength="600" /></label>
            <label class="digital-consent"><input v-model="modal.consent" type="checkbox" required>我有权使用此素材生成数字课程。</label>
          </template>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <footer class="actions"><button type="button" class="button subtle" :disabled="busy" @click="modal = null">取消</button>
          <button class="button primary" :disabled="busy">{{ busy ? '正在处理…' : modal.kind === 'delete' ? '确认删除' : '确认' }}</button></footer>
      </form>
    </Modal>
  </div>
</template>
