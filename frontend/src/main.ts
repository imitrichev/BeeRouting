import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import 'maplibre-gl/dist/maplibre-gl.css'

import App from './App.vue'
import './style.css'

const vuetify = createVuetify({
  // Без явной регистрации Vue оставляет v-btn, v-card и другие v-* теги
  // неизвестными HTML-элементами: текст виден, но оформление и поведение
  // компонентов Vuetify отсутствуют.
  components,
  directives,
  theme: {
    defaultTheme: 'light',
  },
})

createApp(App).use(vuetify).mount('#app')
