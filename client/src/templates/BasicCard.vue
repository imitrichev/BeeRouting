<script setup lang="ts">
interface IProps {
  title?: string
}

const props = withDefaults(defineProps<IProps>(), {
  title: ''
})
</script>

<template>
  <v-card class="elevation-2 rounded-lg" min-height="100" min-width="100">
    <v-card-title v-if="props.title" class="my-1">{{ props.title }}</v-card-title>
    <slot />
  </v-card>
</template>

<style scoped lang="scss">

</style>
