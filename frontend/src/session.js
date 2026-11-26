import { ref, computed } from 'vue'
import { api } from './api'

export const user = ref(null)
export const courseId = ref(Number(sessionStorage.getItem('dianoia-course')) || null)
export const course = computed(() => user.value?.courses.find((entry) => entry.id === courseId.value))

export function changeCourse(value) {
  courseId.value = value ? Number(value) : null
  if (value) sessionStorage.setItem('dianoia-course', String(value))
  else sessionStorage.removeItem('dianoia-course')
}

export function useProfile(profile) {
  user.value = profile
  if (!course.value) changeCourse(profile?.courses[0]?.id)
}

async function requestSession(path, options) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 10000)
  try {
    return await api(path, { ...options, signal: controller.signal })
  } catch (failure) {
    if (controller.signal.aborted) throw new Error('后端响应超时，请稍后重试')
    if (failure instanceof TypeError) throw new Error('无法连接后端，请检查服务是否运行')
    throw failure
  } finally {
    clearTimeout(timer)
  }
}

export async function restore(role) {
  try {
    const profile = await requestSession('/auth/me')
    if (profile.role === role) useProfile(profile)
  } catch (error) {
    if (error.status !== 401) throw error
  }
}

export async function signIn(credentials) {
  useProfile(await requestSession('/auth/login', { method: 'POST', body: credentials }))
}

export async function logout() {
  await api('/auth/logout', { method: 'POST' })
  useProfile(null)
}

export const theme = ref(localStorage.getItem('dianoia-theme') === 'light' ? 'light' : 'dark')

export function applyTheme() {
  document.documentElement.dataset.theme = theme.value
}

export function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('dianoia-theme', theme.value)
  applyTheme()
}
