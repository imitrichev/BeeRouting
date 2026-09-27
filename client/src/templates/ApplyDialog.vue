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
  <v-dialog :model-value="true" opacity="0.8" persistent :max-width="380">
    <v-card class="px-4 py-3 elevation-2">
      <v-form class="w-100" @submit.prevent="emit('close', true)">
        <div class="d-flex flex-column ga-3 mb-3 mt-1">
          <span class="text-body-1 text-center">{{ props.text }}</span>
          <slot />
        </div>

        <v-divider class="mb-3" />

        <v-row no-gutters class="justify-end w-100 ga-2">
          <v-btn
            variant="text"
            class="text-none"
            :loading="props.loading"
            @click="emit('close', false)"
          >
            {{ props.denyText }}
          </v-btn>
          <v-btn
            variant="flat"
            color="primary"
            class="text-none px-4"
            :loading="props.loading"
            type="submit"
          >
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
