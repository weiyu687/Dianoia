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

export async function restore(role) {
  try {
    const profile = await api('/auth/me')
    if (profile.role === role) useProfile(profile)
  } catch (error) {
    if (error.status !== 401) throw error
  }
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
