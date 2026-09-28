<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'
import logo from '@/assets/logo.svg'

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
    <v-app-bar-title class="pr-3">
      <v-row no-gutters class="justify-start align-center text-no-wrap">
        <v-img :src="logo" width="40" height="40" max-width="40" max-height="40" class="mr-3" />
        BeeRouting
      </v-row>
    </v-app-bar-title>
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
