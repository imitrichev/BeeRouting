<script setup lang="ts">
/**
 * Универсальная карточка-контейнер с опциональной шапкой и подвалом.
 *
 * Используется как обёртка для секций страницы (метрики, таблицы, списки).
 * Поддерживает:
 * - заголовок и слот `toolbarAppend` в шапке (шапка рендерится, если задан
 *   заголовок или `showToolbar`);
 * - слот `loading`, отображаемый вместо основного контента во время загрузки;
 * - слот по умолчанию для основного содержимого;
 * - слот `bottom` в подвале (рендерится при `showBottom`).
 */

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Заголовок карточки. Пустая строка — заголовок не отображается. */
  title?: string
  /** Показывать шапку даже без заголовка (например, только для `toolbarAppend`). */
  showToolbar?: boolean
  /** Показывать подвал с содержимым слота `bottom`. */
  showBottom?: boolean
  /** Флаг загрузки: вместо основного контента рендерится слот `loading`. */
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
    <!-- Шапка: заголовок + слот toolbarAppend -->
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

    <!-- Состояние загрузки (заменяет основной контент) -->
    <slot name="loading" v-if="props.loading" />

    <!-- Основной контент -->
    <slot />

    <!-- Подвал -->
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
