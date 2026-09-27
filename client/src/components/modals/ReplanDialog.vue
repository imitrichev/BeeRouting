<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
}

const props = defineProps<IProps>()

const store = useDistrictDataStore()
const loading = computed(() => store.loadingReplan)

const replan = async () => {
  // TODO: вызвать метод перепланирования в сторе
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600">
    <basic-card title="Перепланирование заявок" :show-bottom="true">
      <template #toolbarAppend>
        <icon-button
          icon="close"
          class="ml-3"
          :loading="loading"
          @click="emit('close')"
          tooltip-text="Закрыть"
        />
      </template>
      <v-row no-gutters class="overflow-list default-scrollbar px-4 py-4">
        <!-- TODO: содержимое диалога -->
      </v-row>
      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn
            :loading="loading"
            color="primary"
            variant="flat"
            class="text-none"
            @click="replan"
          >
            Подтвердить
          </v-btn>
        </v-row>
      </template>
    </basic-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}
</style>
