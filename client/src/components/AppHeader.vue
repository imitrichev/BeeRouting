<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'

const theme = useTheme()

const isDark = computed({
  get: () => theme.global.current.value.dark,
  set: (value: boolean) => {
    theme.global.name.value = value ? 'dark' : 'light'
  },
})
</script>

<template>
  <v-app-bar flat border>
    <v-app-bar-title class="pr-3">BeeRouting</v-app-bar-title>
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
:deep(.v-switch .v-label) {
  display: none;
}
</style>
