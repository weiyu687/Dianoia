<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { Mic, Square } from 'lucide-vue-next'

const emit = defineEmits(['recorded'])
const active = ref(false)
const waiting = ref(false)
const seconds = ref(0)
const error = ref('')
const preview = ref('')
let recorder, stream, timer, start, disposed

function clear() {
  clearInterval(timer)
  stream?.getTracks().forEach((track) => track.stop())
}

function stop() {
  if (recorder?.state === 'recording') recorder.stop()
}

async function record() {
  error.value = ''
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    error.value = '录音需要 HTTPS 或本地浏览器环境，也可以直接上传音频。'
    return
  }
  waiting.value = true
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
    if (disposed) { clear(); return }
    if (preview.value) URL.revokeObjectURL(preview.value)
    preview.value = ''
    emit('recorded', null)
    const chunks = []
    recorder = new MediaRecorder(stream, { audioBitsPerSecond: 96000 })
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data) }
    recorder.onstop = () => {
      const elapsed = performance.now() - start
      clear()
      active.value = false
      if (disposed) return
      if (elapsed < 3000) { error.value = '请录制至少 3 秒。'; return }
      const type = recorder.mimeType
      const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'
      const file = new File(chunks, 'recording.' + ext, { type })
      preview.value = URL.createObjectURL(file)
      emit('recorded', file)
    }
    recorder.onerror = () => { clear(); active.value = false; error.value = '录音失败，请重试或上传音频。' }
    recorder.start()
    start = performance.now()
    active.value = true
    seconds.value = 0
    timer = setInterval(() => {
      seconds.value = Math.floor((performance.now() - start) / 1000)
      if (performance.now() - start >= 29500) stop()
    }, 100)
  } catch {
    clear()
    error.value = '无法访问麦克风，请检查浏览器权限，或直接上传音频。'
  } finally { waiting.value = false }
}

onBeforeUnmount(() => {
  disposed = true
  stop()
  clear()
  if (preview.value) URL.revokeObjectURL(preview.value)
})
</script>

<template>
  <div class="digital-recorder">
    <button v-if="active" type="button" class="button secondary" @click="stop"><Square :size="15" /> 停止录音 · {{ seconds }} 秒</button>
    <button v-else type="button" class="button secondary" :disabled="waiting" @click="record"><Mic :size="15" />{{ preview ? '重新录制' : '开始录制' }}</button>
    <audio v-if="preview" :src="preview" controls aria-label="试听刚录制的样本" />
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
