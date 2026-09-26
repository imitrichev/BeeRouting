<script setup lang="ts">
interface IProps {
  title?: string
  showToolbar?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  title: '',
  loading: false,
  showToolbar: false,
})
</script>

<template>
  <v-card class="elevation-2 rounded-lg">
    <v-toolbar
      density="compact"
      class="elevation-0"
      border
      color="white"
      v-if="!!props.title || props.showToolbar"
    >
      <v-card-title v-if="props.title" class="my-1">
        {{ props.title }}
      </v-card-title>
      <template #append>
        <slot name="toolbarAppend" />
      </template>
    </v-toolbar>
    <slot name="loading" v-if="props.loading" />
    <slot />
  </v-card>
</template>

<style scoped lang="scss"></style>
