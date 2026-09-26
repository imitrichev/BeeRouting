<script setup lang="ts">
const emit = defineEmits<{
  close: [applied: boolean]
}>()

interface IProps {
  text?: string
  applyText?: string
  denyText?: string
  loading?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  text: 'Вы уверены, что хотите совершить данное действие?',
  applyText: 'Да',
  denyText: 'Отмена',
  loading: false,
})
</script>

<template>
  <v-dialog :model-value="true" opacity="0.8" persistent :max-width="350">
    <v-card class="pa-3 elevation-2">
      <v-form class="w-100" @submit.prevent="emit('close', true)">
        <v-row class="w-100 ga-1 mb-4 mt-2 px-3">
          <span class="text-center font-size-16">{{ props.text }}</span>

          <slot />
        </v-row>
        <v-divider class="mb-3"></v-divider>
        <v-row no-gutters class="justify-end w-100">
          <v-btn class="px-3 mr-3" :loading="loading" @click="emit('close', false)">
            {{ props.denyText }}
          </v-btn>
          <v-btn class="form-btn form-btn px-3 mr-3" :loading="loading" type="submit">
            {{ props.applyText }}
          </v-btn>
        </v-row>
      </v-form>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.form-container {
  overflow-y: auto;
  max-height: calc(100vh - 48px - 48px - 48px - 48px - 22px);
}
</style>
