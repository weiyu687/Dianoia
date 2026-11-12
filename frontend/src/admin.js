import { createApp } from 'vue'
import Admin from './Admin.vue'
import { applyTheme } from './session'
import './style.css'

applyTheme()
createApp(Admin).mount('#app')
