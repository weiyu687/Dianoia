<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight, Film, FolderOpen, Mic, Plus, Upload, UserRound } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import CourseRecorder from '../components/CourseRecorder.vue'
import Modal from '../components/Modal.vue'
import { courseId } from '../session'
import '../digitalCourses.css'

const workspace = '/digital-courses'
const router = useRouter()
const projects = ref([])
const assets = ref([])
const folders = ref([])
const requestedTab = useRoute().query.tab
const tab = ref(['avatar', 'voice'].includes(requestedTab) ? requestedTab : 'projects')
const source = ref(useRoute().query.source === 'mine' ? 'mine' : 'official')
const modal = ref(null)
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const formError = ref('')
const grouped = computed(() => new Set(folders.value.flatMap((folder) => folder.samples.map((sample) => sample.id))))
const visibleAssets = computed(() => assets.value.filter((asset) => asset.kind === tab.value &&
  asset.preset === (source.value === 'official') && !grouped.value.has(asset.id)))
const suggestedText = '同学们好，欢迎来到今天的课堂。我们先回顾上一节的内容，再一起完成两个练习。'
const media = (id) => '/api' + workspace + '/assets/' + id + '/preview'
const tabs = [
  { key: 'projects', label: '课程项目', icon: Film },
  { key: 'avatar', label: '形象库', icon: UserRound },
  { key: 'voice', label: '音色与样本库', icon: Mic },
]

onMounted(async () => {
  try {
    [projects.value] = await Promise.all([api(workspace + '?course_id=' + courseId.value), reloadAssets()])
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

async function reloadAssets() {
  [assets.value, folders.value] = await Promise.all([api(workspace + '/assets'), api(workspace + '/voice-folders')])
}

function open(kind, asset = null) {
  modal.value = { kind, asset, name: asset?.name || '', transcript: '', consent: false, mode: 'file', recorded: null,
    folderId: kind === 'assign' ? folders.value[0]?.id : '' }
  formError.value = ''
}

async function reference(folder, sample) {
  formError.value = ''
  error.value = ''
  try {
    const updated = await api(workspace + '/voice-folders/' + folder.id, { method: 'PUT', body: { name: folder.name, reference_id: sample.id } })
    folders.value = folders.value.map((item) => item.id === updated.id ? updated : item)
  } catch (failure) { error.value = failure.message }
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
    } else if (current.kind === 'folder' || current.kind === 'rename-folder' || current.kind === 'delete-folder') {
      const endpoint = workspace + '/voice-folders' + (current.asset ? '/' + current.asset.id : '')
      await api(endpoint, {
        method: { folder: 'POST', 'rename-folder': 'PUT', 'delete-folder': 'DELETE' }[current.kind],
        body: current.kind === 'delete-folder' ? undefined : { name: current.name, reference_id: current.asset?.reference_id },
      })
    } else if (current.kind === 'assign') {
      await api(workspace + '/voice-folders/' + current.folderId + '/samples/' + current.asset.id, { method: 'POST' })
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
      if (current.kind === 'voice' && current.asset) body.set('folder_id', current.asset.id)
      if (current.kind === 'voice' && current.mode === 'record') {
        if (!current.recorded) throw new Error('请先完成录音')
        body.set('file', current.recorded)
      }
      await api(workspace + '/assets', { method: 'POST', body })
    }
    await reloadAssets()
    source.value = 'mine'
    modal.value = null
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="page digital-courses">
    <header class="page-heading">
      <div><h1>数字课程</h1><p>导入课件，逐页编排讲稿，制作带数字讲师的视频。</p></div>
      <button class="button primary" @click="open(tab === 'voice' ? 'folder' : tab)"><Plus :size="17" />{{ { projects: '导入课件', avatar: '上传形象', voice: '新建声音档案' }[tab] }}</button>
    </header>
    <nav class="digital-tabs" aria-label="数字课程工作区">
      <button v-for="item in tabs" :key="item.key" class="button" :class="tab === item.key ? 'secondary' : 'subtle'"
        :aria-pressed="tab === item.key" @click="tab = item.key"><component :is="item.icon" :size="16" />{{ item.label }}</button>
    </nav>
    <nav v-if="tab !== 'projects'" class="digital-tabs" aria-label="素材来源">
      <button class="button" :class="source === 'official' ? 'secondary' : 'subtle'" :aria-pressed="source === 'official'" @click="source = 'official'">官方素材</button>
      <button class="button" :class="source === 'mine' ? 'secondary' : 'subtle'" :aria-pressed="source === 'mine'" @click="source = 'mine'">我的素材</button>
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
    <template v-else>
    <section v-if="tab === 'voice' && source === 'mine'" class="digital-voice-folders">
      <article v-for="folder in folders" :key="folder.id" class="panel digital-folder">
        <header class="section-heading">
          <div><h3><FolderOpen :size="18" /> {{ folder.name }}</h3><small>{{ folder.samples.length }} 条样本</small></div>
          <div class="actions"><button class="button secondary" @click="open('voice', folder)"><Plus :size="15" /> 添加样本</button>
            <button class="button subtle" @click="open('rename-folder', folder)">重命名档案</button>
            <button class="button subtle danger-text" @click="open('delete-folder', folder)">删除档案</button></div>
        </header>
        <p v-if="!folder.samples.length" class="muted">录制或上传一条样本后，即可在编辑器选择此档案。</p>
        <div v-for="sample in folder.samples" :key="sample.id" class="digital-sample">
          <div><strong>{{ sample.name }}</strong><small v-if="folder.reference_id === sample.id"> · 合成参考</small><p>{{ sample.transcript }}</p></div>
          <audio :src="media(sample.id)" controls preload="none" :aria-label="'试听 ' + sample.name" />
          <div class="actions">
            <button v-if="folder.reference_id !== sample.id" class="button secondary" @click="reference(folder, sample)">设为参考</button>
            <button class="button subtle" @click="open('rename', sample)">重命名</button>
            <button class="button subtle danger-text" @click="open('delete', sample)">删除</button>
          </div>
        </div>
      </article>
      <p v-if="!folders.length && !visibleAssets.length" class="empty-state">新建声音档案后，可以录制或上传多条样本。</p>
      <h2 v-if="visibleAssets.length">未归档样本</h2>
    </section>
    <section class="digital-assets">
      <article v-for="asset in visibleAssets" :key="asset.id" class="panel digital-asset">
        <img v-if="asset.kind === 'avatar'" :src="media(asset.id)" :alt="asset.name">
        <audio v-else :src="media(asset.id)" controls :preload="asset.preset ? 'metadata' : 'none'" :aria-label="asset.name" />
        <div><h3>{{ asset.name }}</h3><small>{{ asset.preset ? '预设' : '我的素材' }}</small></div>
        <p v-if="asset.transcript">{{ asset.transcript }}</p>
        <div v-if="!asset.preset" class="actions">
          <button v-if="asset.kind === 'voice' && folders.length" class="button secondary" @click="open('assign', asset)">归入档案</button>
          <button class="button subtle" @click="open('rename', asset)">重命名</button>
          <button class="button subtle danger-text" @click="open('delete', asset)">删除</button></div>
      </article>
      <p v-if="!visibleAssets.length && (tab !== 'voice' || source !== 'mine')" class="empty-state">暂无可用素材。</p>
    </section>
    </template>
    <Modal :open="!!modal" :title="modal ? { projects: '导入课件', avatar: '上传形象', voice: '添加声音样本', rename: '重命名素材', delete: '删除素材',
      folder: '新建声音档案', 'rename-folder': '重命名档案', 'delete-folder': '删除声音档案', assign: '归入声音档案' }[modal.kind] : ''"
      @close="!busy && (modal = null)">
      <form v-if="modal" class="form digital-form" @submit.prevent="submit">
        <template v-if="modal.kind === 'projects'">
          <label>PowerPoint 课件<input name="file" type="file" accept=".ppt,.pptx" required></label>
          <p class="muted">最多 40 页、50 MB。导入后可以逐页预览。</p>
        </template>
        <p v-else-if="modal.kind === 'delete'">确定删除「{{ modal.asset.name }}」？</p>
        <p v-else-if="modal.kind === 'delete-folder'">确定删除「{{ modal.asset.name }}」？样本将移到「未归档样本」。</p>
        <label v-else-if="modal.kind === 'assign'">声音档案<select v-model="modal.folderId" required>
          <option v-for="folder in folders" :key="folder.id" :value="folder.id">{{ folder.name }}</option>
        </select></label>
        <label v-else-if="['folder', 'rename-folder'].includes(modal.kind)">档案名称<input v-model="modal.name" required maxlength="100"></label>
        <template v-else>
          <label>素材名称<input v-model="modal.name" name="name" required maxlength="100"></label>
          <template v-if="modal.kind !== 'rename'">
            <div v-if="modal.kind === 'voice'" class="actions">
              <button type="button" class="button" :class="modal.mode === 'file' ? 'secondary' : 'subtle'" @click="modal.mode = 'file'; modal.recorded = null">上传音频</button>
              <button type="button" class="button" :class="modal.mode === 'record' ? 'secondary' : 'subtle'" @click="modal.mode = 'record'">录制音频</button>
            </div>
            <label v-if="modal.mode === 'file'">{{ modal.kind === 'avatar' ? '形象照片' : '语音样本' }}
              <input type="file" name="file" :accept="modal.kind === 'avatar' ? '.png,.jpg,.jpeg' : '.wav,.mp3'" required></label>
            <CourseRecorder v-else @recorded="modal.recorded = $event" />
            <p class="muted">{{ modal.kind === 'avatar' ? 'PNG 或 JPG，建议使用背景简洁、光线均匀的单人正面照片。' : '支持 3 至 30 秒。建议同一位讲师在安静环境下自然朗读 6 至 15 秒，避免音乐、混响或多人说话。' }}</p>
            <button v-if="modal.kind === 'voice'" type="button" class="button subtle" @click="modal.transcript = suggestedText">使用参考朗读文案</button>
            <label v-if="modal.kind === 'voice'">样本中实际朗读的内容<textarea v-model="modal.transcript" name="transcript" rows="3" required maxlength="600" /></label>
            <label class="digital-consent"><input v-model="modal.consent" type="checkbox" required>我有权使用此素材生成数字课程。</label>
          </template>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <footer class="actions"><button type="button" class="button subtle" :disabled="busy" @click="modal = null">取消</button>
          <button class="button primary" :disabled="busy">{{ busy ? '正在处理…' : modal.kind.startsWith('delete') ? '确认删除' : '确认' }}</button></footer>
      </form>
    </Modal>
  </div>
</template>
