import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import { applyTheme } from './session'
import Teacher from './Teacher.vue'
import Home from './views/Home.vue'
import Library from './views/Library.vue'
import Lessons from './views/Lessons.vue'
import './style.css'

applyTheme()
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/resources', name: 'library', component: Library },
    { path: '/resources/:id', name: 'resource', component: () => import('./views/Resource.vue') },
    { path: '/lessons', name: 'lessons', component: Lessons },
    { path: '/lessons/:id', name: 'lesson', component: () => import('./views/LessonEditor.vue') },
    { path: '/lesson-templates', name: 'lessonTemplates', component: () => import('./views/LessonTemplates.vue') },
    { path: '/exams', name: 'exams', component: () => import('./views/Exams.vue') },
    { path: '/exams/:id', name: 'exam', component: () => import('./views/ExamEditor.vue') },
    { path: '/presentations', name: 'presentations', component: () => import('./views/Presentations.vue') },
    { path: '/presentations/:id', name: 'presentation', component: () => import('./views/PresentationEditor.vue') },
    { path: '/exam-templates', name: 'examTemplates', props: { exam: true }, component: () => import('./views/LessonTemplates.vue') },
    { path: '/mind-maps', name: 'mindMaps', component: () => import('./views/MindMaps.vue') },
    { path: '/mind-maps/:id', name: 'mindMap', component: () => import('./views/MindMapEditor.vue') },
    { path: '/mind-map-templates/:id', name: 'mindMapTemplate', component: () => import('./views/MindMapEditor.vue') },
    { path: '/agent', name: 'agent', component: () => import('./views/Agent.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
createApp(Teacher).use(router).mount('#app')
