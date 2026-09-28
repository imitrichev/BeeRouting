<script setup lang="ts">
/**
 * Шапка приложения.
 *
 * Содержит логотип и название «BeeRouting», а также переключатель
 * светлой/тёмной темы Vuetify. Состояние темы хранится глобально
 * и не сохраняется между сессиями.
 */

import { computed } from 'vue'
import { useTheme } from 'vuetify'
import logo from '@/assets/logo.svg'

const theme = useTheme()

/**
 * Двусторонняя привязка для переключателя темы:
 * чтение — текущее значение тёмной темы, запись — переключение темы Vuetify.
 */
const isDark = computed({
  get: () => theme.global.current.value.dark,
  set: (value: boolean) => {
    theme.global.name.value = value ? 'dark' : 'light'
  },
})
</script>

<template>
  <v-app-bar flat border>
    <v-app-bar-title class="pr-3">
      <v-row no-gutters class="justify-start align-center text-no-wrap">
        <v-img :src="logo" width="40" height="40" max-width="40" max-height="40" class="mr-3" />
        BeeRouting
      </v-row>
    </v-app-bar-title>

    <!-- Переключатель светлой/тёмной темы -->
    <v-switch
      v-model="isDark"
      hide-details
      inset
      density="comfortable"
      color="primary"
      :prepend-icon="isDark ? 'mode_night' : 'light_mode'"
      class="mr-4"
    />
  </v-app-bar>
</template>

<style scoped lang="scss">
/** Скрывает текстовую метку переключателя темы (остаётся только сам свитч). */
:deep(.v-switch .v-label) {
  display: none;
}
</style>
