<script setup>
import { onMounted, ref } from 'vue'
import { BookOpen, House, LibraryBig, LogOut, MessageCircle, PanelLeft } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { changeCourse, courseId, logout, restore, user } from './session'
import Brand from './components/Brand.vue'
import Login from './components/Login.vue'
import ThemeButton from './components/ThemeButton.vue'

const route = useRoute()
const router = useRouter()
const ready = ref(false)
const error = ref('')
const navigationOpen = ref(false)
const items = [
  { to: '/', label: '首页', icon: House, routes: ['home'] },
  { to: '/resources', label: '资料库', icon: LibraryBig, routes: ['library', 'resource'] },
  { to: '/lessons', label: '教案', icon: BookOpen, routes: ['lessons', 'lesson', 'lessonTemplates'] },
  { to: '/agent', label: '教师 Agent', icon: MessageCircle, routes: ['agent'] },
]

onMounted(async () => {
  try { await restore('teacher') }
  catch (failure) { error.value = failure.message }
  finally { ready.value = true }
})

function selectCourse(event) {
  changeCourse(event.target.value)
  if (route.name === 'resource') router.push('/resources')
  if (route.name === 'lesson') router.push('/lessons')
}

async function signOut() {
  try { await logout(); router.replace('/') }
  catch (failure) { error.value = failure.message }
}
</script>

<template>
  <div v-if="!ready" class="full-state" role="status">正在加载工作台</div>
  <Login v-else-if="!user" role="teacher" />
  <div v-else class="teacher-shell" :class="{ 'nav-open': navigationOpen }">
    <aside class="navigation">
      <Brand />
      <nav aria-label="教师功能">
        <RouterLink v-for="item in items" :key="item.to" :to="item.to"
          :class="{ selected: item.routes.includes(route.name) }" @click="navigationOpen = false">
          <component :is="item.icon" :size="19" />{{ item.label }}
        </RouterLink>
      </nav>
      <div class="navigation-bottom">
        <ThemeButton label />
        <div class="account-line"><span class="avatar">{{ user.name[0] }}</span><span>{{ user.name }}</span>
          <button class="button subtle icon-only" aria-label="退出登录" @click="signOut"><LogOut :size="16" /></button>
        </div>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div class="actions">
          <button class="button subtle icon-only menu-button" aria-label="切换导航" :aria-expanded="navigationOpen" @click="navigationOpen = !navigationOpen"><PanelLeft :size="19" /></button>
          <span class="workspace-label">教师工作台</span>
        </div>
        <label v-if="user.courses.length" class="course-select"><span>当前课程</span><select aria-label="当前课程" :value="courseId" @change="selectCourse">
          <option v-for="item in user.courses" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select></label>
      </header>
      <p v-if="error" role="alert" class="error shell-error">{{ error }}</p>
      <main>
        <RouterView v-if="courseId" v-slot="{ Component }"><component :is="Component" :key="`${route.path}:${courseId}`" /></RouterView>
        <div v-else class="full-state">暂无任课课程，请联系学校管理员。</div>
      </main>
    </div>
  </div>
</template>
