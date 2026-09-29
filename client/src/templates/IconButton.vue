<script setup lang="ts">
/**
 * Кнопка-иконка с тултипом.
 *
 * Используется как универсальный элемент управления (например, «добавить»,
 * «обновить»). Поддерживает состояние загрузки, настраиваемую иконку,
 * цвет иконки, CSS-классы и текст подсказки.
 *
 * При клике эмитит событие `click` (без полезной нагрузки).
 */

/**
 * События компонента.
 * `click` — нажатие на кнопку.
 */
const emit = defineEmits<{
  click: []
}>()

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: блокирует кнопку и показывает индикатор. */
  loading?: boolean
  /** Текст всплывающей подсказки. Пустая строка — тултип без текста. */
  tooltipText?: string
  /** Имя иконки (Material Design). */
  icon?: string
  /** Цвет иконки (токен Vuetify или CSS-цвет). */
  color?: string
  /** Дополнительные CSS-классы, навешиваемые на кнопку. */
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
        size="40"
        flat
        :loading="componentProps.loading"
        @click="emit('click')"
      >
        <v-icon :color="componentProps.color">{{ componentProps.icon }}</v-icon>
      </v-btn>
    </template>
  </v-tooltip>
</template>

<style scoped lang="scss"></style>
