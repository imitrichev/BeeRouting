<script setup lang="ts">
/**
 * Модальный диалог подтверждения действия.
 *
 * Отображается как постоянный (`persistent`) диалог шириной до 380px.
 * Содержит текст-вопрос, опциональный слот для дополнительного контента
 * (например, формы) и кнопки «подтвердить» / «отменить».
 *
 * По закрытию (подтверждение или отмена) эмитит событие `close`
 * с булевым признаком применённого действия:
 * - `true` — пользователь подтвердил (кнопка «Да» или submit формы);
 * - `false` — пользователь отменил.
 */

/**
 * События компонента.
 */
const emit = defineEmits<{
  /** Закрытие диалога с результатом: `true` — подтверждено, `false` — отменено. */
  close: [applied: boolean]
}>()

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Текст-вопрос в теле диалога. */
  text?: string
  /** Текст кнопки подтверждения. */
  applyText?: string
  /** Текст кнопки отмены. */
  denyText?: string
  /** Флаг загрузки: показывает индикатор на обеих кнопках и блокирует их. */
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
          <!-- Дополнительный контент: формы, поля ввода и т.п. -->
          <slot />
        </div>

        <v-divider class="mb-3" />

        <v-row no-gutters class="justify-end w-100 ga-2">
          <!-- Отмена -->
          <v-btn
            variant="text"
            class="text-none"
            :loading="props.loading"
            @click="emit('close', false)"
          >
            {{ props.denyText }}
          </v-btn>

          <!-- Подтверждение: submit формы позволяет сработать Enter -->
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
/**
 * Контейнер формы с вертикальной прокруткой при переполнении.
 *
 * Класс в текущем шаблоне не применяется — оставлен для использования
 * родителем/слотом при необходимости ограничить высоту контента.
 */
.form-container {
  overflow-y: auto;
  max-height: calc(100vh - 48px - 48px - 48px - 48px - 22px);
}
</style>
