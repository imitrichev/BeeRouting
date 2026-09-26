<script setup lang="ts">
const emit = defineEmits<{
  click: []
}>()

interface IProps {
  loading?: boolean
  tooltipText?: string
  icon?: string
  color?: string
  class?: string
}

const componentProps = withDefaults(defineProps<IProps>(), {
  loading: false,
  tooltipText: '',
  icon: 'add',
  class: '',
})
</script>

<template>
  <v-tooltip :text="componentProps.tooltipText">
    <template #activator="{ props }">
      <v-btn
        v-bind="props"
        :icon="componentProps.icon"
        :class="componentProps.class"
        :color="componentProps.color"
        size="40"
        flat
        :loading="componentProps.loading"
        @click="emit('click')"
      />
    </template>
  </v-tooltip>
</template>

<style scoped lang="scss"></style>
