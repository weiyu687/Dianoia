<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Eye } from 'lucide-vue-next'
import { api } from '../api'
import { sectionsFlat } from '../questionBanks'
import BankCover from '../components/BankCover.vue'
import BankQuestionPreview from '../components/BankQuestionPreview.vue'
import '../questionBanks.css'
const route = useRoute()
const data = ref(null)
const error = ref('')
const chapter = ref('')
const page = ref(1)
const filtered = computed(() => {
  if (!data.value) return []
  const ids = new Set([chapter.value])
  for(let i=0;i<8;i++) for(const s of data.value.sections) if(ids.has(s.parent_id)) ids.add(s.id)
  return data.value.questions.filter((item) => !chapter.value || ids.has(item.question.section_id))
})
const visible = computed(() => filtered.value.slice((page.value-1)*10,page.value*10))
onMounted(async () => { try { data.value = await api(`/question-banks/${route.params.id}/preview`+(route.query.release_id?'?release_id='+encodeURIComponent(route.query.release_id):'')) } catch(failure) {error.value=failure.message} })
</script>
<template>
  <div class="page bank-preview-page"><RouterLink class="text-link back-link" :to="'/question-banks/'+route.params.id"><ArrowLeft :size="16" />返回编辑</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="data"><div class="bank-preview-banner"><Eye :size="17" />学生视角预览 · {{ data.release ? '发布版本 v'+data.release.number : '当前草稿' }} · 此处输入仅用于预览</div>
      <section class="panel bank-preview-intro"><BankCover :bank="data" :course="data.course_name || ''" /><div class="stack"><h1>{{ data.title }}</h1><p class="muted">{{ data.description || '按章节自主练习，随时查看参考答案与解析。' }}</p><p>{{ data.questions.length }} 道练习题</p></div></section>
      <div class="bank-preview-layout"><aside class="panel"><h3>章节</h3><button :class="{active:!chapter}" @click="chapter='';page=1">全部题目</button><button v-for="s in sectionsFlat(data.sections)" :key="s.id" :style="{paddingLeft:14+s.depth*16+'px'}" :class="{active:chapter===s.id}" @click="chapter=s.id;page=1">{{ s.title }}</button></aside>
        <div class="stack"><BankQuestionPreview v-for="(item,index) in visible" :key="item.version_id" :item="item" :materials="data.materials" :number="(page-1)*10+index+1" />
          <p v-if="!visible.length" class="empty-state">此章节暂无参与发布的题目。</p>
          <div class="bank-pagination"><button class="button secondary" :disabled="page===1" @click="page--">上一页</button><span>{{ page }} / {{ Math.max(1,Math.ceil(filtered.length/10)) }}</span><button class="button secondary" :disabled="page*10>=filtered.length" @click="page++">下一页</button></div></div></div>
    </template>
  </div>
</template>
