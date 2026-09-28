/**
 * Точка входа приложения.
 *
 * Создаёт экземпляр Vue-приложения, подключает глобальные плагины
 * (Vuetify и Pinia), глобальные стили и монтирует корневой компонент
 * `App` в элемент `#app`.
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import '@/styles/index.scss'
import { vuetify } from '@/plugins'

const app = createApp(App)

app.use(vuetify)
app.use(createPinia())

app.mount('#app')
