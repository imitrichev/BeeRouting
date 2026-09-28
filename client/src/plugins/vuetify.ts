/**
 * Конфигурация и инициализация Vuetify.
 *
 * Регистрирует все компоненты и директивы Vuetify, подключает набор иконок
 * Material Design (`md`), а также задаёт тему оформления. Тема `dark`
 * используется по умолчанию; тема `light` объявлена, но пока без кастомных
 * цветов (будут взяты значения по умолчанию).
 *
 * Экспортируется готовый экземпляр Vuetify, который подключается в `main.ts`.
 */

import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import { aliases, md } from 'vuetify/iconsets/md'

export default createVuetify({
  /** Глобальная регистрация всех компонентов Vuetify. */
  components,
  /** Глобальная регистрация всех директив Vuetify. */
  directives,
  /** Настройка набора иконок: Material Design по умолчанию, с алиасами. */
  icons: {
    defaultSet: 'md',
    aliases,
    sets: {
      md,
    },
  },
  /** Настройка тем оформления. */
  theme: {
    /** Тема по умолчанию — тёмная. */
    defaultTheme: 'dark',
    themes: {
      /** Светлая тема (цвета по умолчанию). */
      light: {
        colors: {},
      },
    },
  },
})
