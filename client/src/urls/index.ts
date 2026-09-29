/**
 * Реестр endpoint'ов API, сгруппированных по доменным областям.
 *
 * Каждая запись содержит путь и HTTP-метод. Пути могут содержать шаблонные
 * сегменты в формате `{param}` (например, `{task_id}`), которые подставляются
 * при формировании конкретного запроса.
 *
 * Модуль экспортирует единственный объект `baseUrls` как default.
 */

import { HTTP_METHODS } from '@/utils/consts.ts'

/**
 * Карта endpoint'ов API.
 */
const baseUrls = {
  /** Справочники (selectors). */
  SELECTORS: {
    /** Список территорий. */
    TERRITORIES: {
      path: '/api/v2/selectors/territories/',
      method: HTTP_METHODS.GET,
    },
    /** Список районов. */
    DISTRICTS: {
      path: '/api/v2/selectors/districts/',
      method: HTTP_METHODS.GET,
    },
    /** Список приоритетов. */
    PRIORITIES: {
      path: '/api/v2/selectors/priorities/',
      method: HTTP_METHODS.GET,
    },
    /** Список навыков. */
    SKILLS: {
      path: '/api/v2/selectors/skills/',
      method: HTTP_METHODS.GET,
    },
    /** Список норм времени. */
    TIME_NORMS: {
      path: '/api/v2/selectors/time-norms/',
      method: HTTP_METHODS.GET,
    },
    /** Список типов транспортных средств. */
    VEHICLE_TYPES: {
      path: '/api/v2/selectors/vehicle-types/',
      method: HTTP_METHODS.GET,
    },
  },
  /** Полный сброс датасета (возврат к официальному набору). */
  RESET_ALL: {
    path: '/api/v2/dataset/official/',
    method: HTTP_METHODS.POST,
  },
  /** Операции над задачами. */
  TASKS: {
    /** Обновление статуса задачи. */
    UPDATE_STATUS: {
      path: '/api/v2/jobs/status/',
      method: HTTP_METHODS.PATCH,
    },
    /** Создание задачи. */
    CREATE: {
      path: '/api/v2/tasks/',
      method: HTTP_METHODS.POST,
    },
    /** Пояснение к остановке маршрута по задаче. */
    EXPLAIN: {
      path: '/api/v2/explain/{task_id}/',
      method: HTTP_METHODS.POST,
    },
    /** Ручное переназначение задачи. */
    REASSIGNMENT: {
      /** Предварительный просмотр переназначения (без применения). */
      PREVIEW: {
        path: '/api/v2/manual-reassignment/preview/',
        method: HTTP_METHODS.POST,
      },
      /** Подтверждение и применение переназначения. */
      CONFIRM: {
        path: '/api/v2/manual-reassignment/confirm/',
        method: HTTP_METHODS.POST,
      },
    },
  },
  /** Операции по району. */
  DISTRICT: {
    /** Получение данных района (датасет + результат). */
    DATA: {
      path: '/api/v2/dataset/',
      method: HTTP_METHODS.GET,
    },
    /** Запуск оптимизации маршрутов. */
    OPTIMIZE: {
      path: '/api/v2/optimize/',
      method: HTTP_METHODS.POST,
    },
    /** Перепланирование при событии (инженер недоступен, отмена задачи, экстренная задача). */
    REPLAN: {
      path: '/api/v2/replan/',
      method: HTTP_METHODS.POST,
    },
  },
}

export default baseUrls
