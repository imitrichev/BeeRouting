<script setup lang="ts">
interface IProps {
  title?: string
  loading?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  title: '',
  loading: false,
})
</script>

<template>
  <v-card class="elevation-2 rounded-lg">
    <v-card-title v-if="props.title" class="my-1">{{ props.title }}</v-card-title>
    <slot name="loading" v-if="props.loading" />
    <slot v-else />
  </v-card>
</template>

<style scoped lang="scss"></style>
