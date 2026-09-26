<script setup lang="ts">
interface IProps {
  title?: string
  showToolbar?: boolean
  showBottom?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  title: '',
  loading: false,
  showToolbar: false,
  showBottom: false,
})
</script>

<template>
  <v-card class="elevation-2 rounded-lg">
    <v-row
      no-gutters
      class="elevation-0 px-4 py-3 border-bottom align-center"
      v-if="!!props.title || props.showToolbar"
    >
      <v-col v-if="props.title" class="text-pre-wrap text-body-large font-weight-bold">
        {{ props.title }}
      </v-col>
      <slot name="toolbarAppend" />
    </v-row>
    <slot name="loading" v-if="props.loading" />
    <slot />
    <v-row
      no-gutters
      class="elevation-0 px-4 py-3 border-bottom align-center"
      v-if="props.showBottom"
    >
      <v-col>
        <slot name="bottom" />
      </v-col>
    </v-row>
  </v-card>
</template>

<style scoped lang="scss"></style>
