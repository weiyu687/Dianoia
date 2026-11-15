<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, formatSize } from '../api'

const props = defineProps({ endpoint: { type: String, required: true }, kind: { type: String, required: true }, current: String })
const emit = defineEmits(['attach', 'busy'])
const assets = ref([])
const selection = ref(props.current || '')
const loading = ref(true)
const uploading = ref(false)
const error = ref('')
const previewError = ref(false)
const selected = computed(() => assets.value.find((asset) => asset.id === selection.value))
const source = computed(() => selected.value && '/api' + props.endpoint + '/media/' + selected.value.id)
const suffix = props.kind === 'audio' ? '.mp3' : '.mp4'
const tracks = (items) => items.filter((asset) => asset.kind === props.kind)

onMounted(async () => {
  try { assets.value = tracks(await api(props.endpoint + '/media')) }
  catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

async function upload(event) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  if (file.size > 32 * 1024 * 1024) { error.value = '文件不能超过 32 MB'; return }
  uploading.value = true
  emit('busy', true)
  try {
    const body = new FormData()
    body.append('file', file)
    const asset = await api(props.endpoint + '/media?kind=' + props.kind, { method: 'POST', body })
    assets.value = [asset, ...assets.value]
    previewError.value = false
    selection.value = asset.id
  } catch (failure) { error.value = failure.message }
  finally {
    uploading.value = false
    emit('busy', false)
  }
}
</script>

<template>
  <div class="stack">
    <label>上传{{ kind === 'audio' ? '音频（MP3）' : '视频（H.264/AAC MP4）' }}
      <input type="file" :accept="suffix" :disabled="uploading || loading" @change="upload">
    </label>
    <p v-if="uploading" role="status">正在上传并检查格式…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <label v-if="assets.length">已上传到本课程
      <select v-model="selection" :disabled="uploading" @change="previewError = false">
        <option value="">选择文件</option>
        <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.filename }} · {{ formatSize(asset.size) }}</option>
      </select>
    </label>
    <template v-if="source">
      <video v-if="kind === 'video'" :key="source" class="presentation-media-preview" :src="source" controls playsinline preload="metadata"
        aria-label="视频预览" @error="previewError = true" />
      <audio v-else :key="source" class="presentation-media-preview" :src="source" controls preload="metadata"
        aria-label="音频预览" @error="previewError = true" />
      <p v-if="previewError" class="error" role="status">当前浏览器无法预览此文件</p>
    </template>
    <div class="dialog-actions">
      <button type="button" class="button primary" :disabled="!selected || uploading || previewError"
        @click="emit('attach', selected)">{{ current ? '替换文件' : '插入到当前页' }}</button>
    </div>
  </div>
</template>
