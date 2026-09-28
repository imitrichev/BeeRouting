<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Map, Popup, Marker, NavigationControl, GeoJSONSource, LngLatBounds } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { getEngineerColor, hasFiniteCoordinates } from '@/utils/map.ts'
import {
  getPriorityTranslation,
  getSkillTranslation,
  getWordDeclension,
} from '@/utils/translations.ts'
import type { EngineerRoute, RouteStop, Task } from '@/types/entities.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const tasks = computed(() => districtDataStore.getDistrictTasks)
const routes = computed(() => districtDataStore.getRoutes)
const isOptimized = computed(() => districtDataStore.isOptimized)
const selectedRoutes = computed(() => districtDataStore.selectedRoutes)
const districtData = computed(() => districtDataStore.getDistrictData)
const firstLoadingComplete = ref<boolean>(false)

let map: Map | null = null
let markers: Marker[] = []
const container = ref<HTMLElement | null>(null)

const ROUTE_SOURCE_ID = 'routes-source'
const ROUTE_LAYER_ID = 'routes-layer'

const renderMap = () => {
  if (map) return
  if (!container.value) return

  map = new Map({
    container: container.value,
    style: {
      version: 8,
      sources: {
        openstreetmap: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors',
        },
      },
      layers: [
        {
          id: 'openstreetmap',
          type: 'raster',
          source: 'openstreetmap',
        },
      ],
    },
    center: [37.6178, 55.7528],
    zoom: 10,
  })

  map.addControl(
    new NavigationControl({
      showZoom: true,
      showCompass: false,
      visualizePitch: true,
    }),
    'top-right',
  )

  map.on('load', () => {
    if (!map!.getSource(ROUTE_SOURCE_ID)) {
      map!.addSource(ROUTE_SOURCE_ID, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
    }
    if (!map!.getLayer(ROUTE_LAYER_ID)) {
      map!.addLayer({
        id: ROUTE_LAYER_ID,
        type: 'line',
        source: ROUTE_SOURCE_ID,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.8 },
      })
    }

    renderTasks()
    recompileRoutesData()
  })
}

const createDepotMarkerElement = (): HTMLElement => {
  const element = document.createElement('div')
  element.className = 'depot-marker'
  element.setAttribute('aria-label', 'Депо')
  element.innerHTML = `
    <span class="depot-marker-shape">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 10.5 12 3l9 7.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19.5v-9Z" />
        <path class="depot-door" d="M9 21v-6h6v6" />
      </svg>
    </span>
  `
  return element
}

const createTaskMarkerElement = (stopIndex: number | undefined, color: string): HTMLElement => {
  const element = document.createElement('div')
  element.className = 'task-marker'
  element.style.setProperty('--marker-color', color)
  element.setAttribute('aria-label', stopIndex ? `Остановка ${stopIndex}` : 'Заявка')
  element.innerHTML = `
    <svg class="task-marker-pin" viewBox="0 0 24 32" aria-hidden="true">
      <path d="M12 0C5.4 0 0 5.4 0 12c0 8.4 12 20 12 20s12-11.6 12-20c0-6.6-5.4-12-12-12Z"
            fill="var(--marker-color, #888)" />
      <circle cx="12" cy="12" r="8" fill="#fff" />
      ${stopIndex ? `<text x="12" y="12" text-anchor="middle" dominant-baseline="middle" font-size="9" font-weight="700" fill="var(--marker-color, #888)">${stopIndex}</text>` : ''}
    </svg>
  `
  return element
}

/** Хелпер: строка "ключ — значение" в попапе */
const popupRow = (label: string, value: string | number | null | undefined): string => {
  if (value === null || value === undefined || value === '') return ''
  return `<div class="map-popup__row"><span class="map-popup__label">${label}</span><span class="map-popup__value">${value}</span></div>`
}

/** Хелпер: заголовок попапа */
const popupTitle = (text: string): string => `<div class="map-popup__title">${text}</div>`

const getTaskMarkerWithPopup = (
  popupContent: string,
  longitude: number,
  latitude: number,
  color: string,
  stopIndex?: number,
): Marker => {
  const popup = new Popup({
    offset: 25,
    className: 'map-popup',
    closeButton: true,
    maxWidth: '280px',
  }).setHTML(`<div class="map-popup__body">${popupContent}</div>`)

  return new Marker({ color, element: createTaskMarkerElement(stopIndex, color) })
    .setLngLat([longitude, latitude])
    .setPopup(popup)
    .addTo(map!)
}

const getNotOptimizedMarker = (
  color: string,
  taskId: string,
  taskType: string,
  taskDuration: number,
  taskWindowStart: string,
  taskWindowEnd: string,
  taskPriority: string,
  taskLongitude: number,
  taskLatitude: number,
): Marker => {
  const content = [
    popupTitle(`Заявка ${taskId}`),
    popupRow('Тип', getSkillTranslation(taskType)),
    popupRow('Длительность', `${taskDuration} мин.`),
    popupRow('Окно', `${taskWindowStart} — ${taskWindowEnd}`),
    popupRow('Приоритет', getPriorityTranslation(taskPriority)),
  ].join('')

  return getTaskMarkerWithPopup(content, taskLongitude, taskLatitude, color)
}

const getOptimizedMarker = (
  color: string,
  taskId: string,
  taskEngineerName: string | null,
  engineerArrival: string,
  engineerServiceStart: string,
  engineerServiceEnd: string,
  engineerTravelTimeFromPrev: number,
  engineerDistanceFromPrev: string,
  taskLongitude: number,
  taskLatitude: number,
  stopIndex: number,
): Marker => {
  const content = [
    popupTitle(`Заявка ${taskId}`),
    taskEngineerName ? popupRow('Назначена', taskEngineerName) : '',
    popupRow('Прибытие', engineerArrival),
    popupRow('Работы', `${engineerServiceStart} — ${engineerServiceEnd}`),
    popupRow('Время от пред.', `${engineerTravelTimeFromPrev} мин.`),
    popupRow('Дистанция от пред.', `${engineerDistanceFromPrev} км.`),
  ].join('')

  return getTaskMarkerWithPopup(content, taskLongitude, taskLatitude, color, stopIndex)
}

const clearMarkers = () => {
  markers.forEach((marker) => marker.remove())
  markers = []
}

const recompileRoutesData = () => {
  if (!map) return

  const source = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
  if (!source) return

  const features = routes.value
    .filter((route) => {
      if (selectedRoutes.value.length === 0) return false
      return selectedRoutes.value.includes(route.engineer_id)
    })
    .map((route) => {
      const g = route.geometry
      if (!g || g.type !== 'LineString') {
        console.warn('[routes] no geometry for', route.engineer_id)
        return null
      }
      if (!Array.isArray(g.coordinates) || g.coordinates.length < 2) return null
      return {
        type: 'Feature' as const,
        properties: {
          engineer_id: route.engineer_id,
          engineer_name: route.engineer_name,
          color: getEngineerColor(route.engineer_id),
        },
        geometry: {
          type: 'LineString' as const,
          coordinates: g.coordinates,
        },
      }
    })
    .filter((f): f is NonNullable<typeof f> => f !== null)

  source.setData({ type: 'FeatureCollection', features })
}

const renderTasks = () => {
  if (!map) return

  clearMarkers()

  const bounds = new LngLatBounds()

  tasks.value.forEach((task) => {
    if (task.latitude === null || task.longitude === null) return

    const getTaskRoute = (task: Task): EngineerRoute | null => {
      for (const route of routes.value) {
        if (route.stops.map((item) => item.task_id).includes(task.id)) {
          return route
        }
      }
      return null
    }

    const getRouteTaskStop = (task: Task, route: EngineerRoute): RouteStop | null => {
      const stops = route.stops.filter((r) => r.task_id === task.id)
      return stops[0] ? stops[0] : null
    }

    const getRouteTaskStopIndex = (route: EngineerRoute, stop: RouteStop): number => {
      for (let i = 0; i < route.stops.length; i++) {
        const routeStopTaskId = route.stops[i]?.task_id
        if (stop.task_id === routeStopTaskId) return i
      }
      return 0
    }

    const getTaskColor = (task: Task): string => {
      if (routes.value.length === 0) return '#888888'
      for (const route of routes.value) {
        const engineerColor = getEngineerColor(route.engineer_id)
        if (route.stops.map((item) => item.task_id).includes(task.id)) {
          if (selectedRoutes.value.includes(route.engineer_id)) return engineerColor
          return '#888888'
        }
      }
      return '#888888'
    }

    const taskRoute = getTaskRoute(task)
    const taskRouteStop = taskRoute ? getRouteTaskStop(task, taskRoute) : null
    const taskRouteStopIndex =
      taskRoute && taskRouteStop ? getRouteTaskStopIndex(taskRoute, taskRouteStop) : null
    const taskColor = getTaskColor(task)

    if (!taskRoute) {
      markers.push(
        getNotOptimizedMarker(
          taskColor,
          task.id,
          task.required_skill,
          task.duration_minutes,
          task.window_start,
          task.window_end,
          task.priority,
          task.longitude,
          task.latitude,
        ),
      )
    } else if (taskRouteStop && taskRouteStopIndex !== null) {
      markers.push(
        getOptimizedMarker(
          taskColor,
          taskRouteStop.task_id,
          `${taskRoute.engineer_name} (#${taskRouteStopIndex + 1})`,
          taskRouteStop.arrival_time,
          taskRouteStop.service_start_time,
          taskRouteStop.service_end_time,
          taskRouteStop.travel_time_from_previous,
          taskRouteStop.distance_from_previous_km.toFixed(2),
          Number(taskRouteStop.longitude),
          Number(taskRouteStop.latitude),
          taskRouteStopIndex + 1,
        ),
      )
    }
    if (!selectedRoutes.value.length || taskColor !== '#888888') {
      bounds.extend([Number(task.longitude), Number(task.latitude)])
    }
  })

  const dataset = districtData.value?.dataset
  if (dataset && hasFiniteCoordinates(dataset.office_latitude, dataset.office_longitude)) {
    const depotMarker = new Marker({
      element: createDepotMarkerElement(),
      anchor: 'bottom',
    })
      .setLngLat([dataset.office_longitude as number, dataset.office_latitude as number])
      .setPopup(
        new Popup({
          offset: 20,
          className: 'map-popup',
          closeButton: true,
          maxWidth: '280px',
        }).setHTML(
          `<div class="map-popup__body">${popupTitle('Офис')}${popupRow(
            'Адрес',
            dataset.office_address ?? 'Адрес не указан',
          )}</div>`,
        ),
      )
      .addTo(map)
    markers.push(depotMarker)
  }

  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 40, maxZoom: 12 })
  }

  recompileRoutesData()
}

watch(
  () => props.loading,
  async (nVal) => {
    if (nVal) {
      clearMarkers()
      if (!map) return
      const source = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
      if (!source) return
      source.setData({ type: 'FeatureCollection', features: [] })
      return
    }
    firstLoadingComplete.value = true
    await nextTick()
    renderMap()
  },
)

watch(
  () => [...selectedRoutes.value],
  () => {
    renderTasks()
    recompileRoutesData()
  },
)

watch(isOptimized, () => {
  renderTasks()
  recompileRoutesData()
})

onBeforeUnmount(() => {
  clearMarkers()
  map?.remove()
  map = null
})

const toggleSelect = (item: EngineerRoute) => {
  districtDataStore.toggleRouteSelection(item.engineer_id)
}

const isSelected = (item: EngineerRoute) => {
  return districtDataStore.isRouteSelected(item.engineer_id)
}

const routesPanelOpen = ref<boolean>(true)
</script>

<template>
  <basic-card :loading="props.loading" title="Карта">
    <template #loading v-if="!firstLoadingComplete">
      <v-skeleton-loader type="article" />
    </template>

    <div class="map-wrapper">
      <div v-if="firstLoadingComplete" ref="container" class="map-container map-container--full" />
      <div v-if="isOptimized" class="routes-overlay">
        <div v-if="routesPanelOpen" class="routes-overlay__panel">
          <div class="routes-overlay__header">
            <span class="text-subtitle-2 font-weight-bold">Маршруты</span>
            <v-btn
              icon="chevron_left"
              size="x-small"
              variant="text"
              density="comfortable"
              @click="routesPanelOpen = false"
            />
          </div>
          <v-list
            class="overflow-list routes-list default-scrollbar py-1 pl-0 pr-2"
            density="compact"
          >
            <v-list-item
              density="compact"
              class="pb-0 pt-1 px-2"
              v-for="item in routes.filter((route) => !!route.stops.length)"
              :key="item.engineer_id"
              :title="item.engineer_name"
              :subtitle="`${item.stops.length} ${getWordDeclension(item.stops.length, 'остановка', 'остановки', 'остановок')}`"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="isSelected(item)"
                  density="comfortable"
                  hide-details
                  class="mr-2"
                  :color="getEngineerColor(item.engineer_id)"
                  @update:model-value="toggleSelect(item)"
                />
              </template>
            </v-list-item>
          </v-list>
        </div>
        <v-btn
          v-else
          icon="route"
          size="small"
          class="routes-overlay__toggle"
          @click="routesPanelOpen = true"
        />
      </div>
    </div>
  </basic-card>
</template>

<style scoped lang="scss">
.map-container {
  width: 100% !important;
  min-height: 292px !important;
  height: calc(100vh - 300px) !important;
  max-height: 100vw !important;
}

.map-wrapper {
  position: relative;
  width: 100%;
}

.overflow-list {
  min-height: 192px !important;
  height: auto !important;
  max-height: min(100vh - 300px - 100px, 100vw - 100px) !important;
}

.routes-list {
  background: transparent !important;
}

.routes-overlay {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 5;
  max-height: calc(100% - 24px);
  display: flex;
  align-items: flex-start;
}

.routes-overlay__panel {
  width: min(260px, 100vw - 100px);
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.routes-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px 8px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.routes-overlay__panel :deep(.v-list) {
  overflow-y: auto;
  max-height: 100%;
}

.routes-overlay__toggle {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
}

.v-theme--dark .routes-overlay__panel {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
}

/* Плавное появление/скрытие */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* --- Попапы MapLibre --- */
:deep(.map-popup .maplibregl-popup-content) {
  position: relative;
  background: var(--map-popup-bg, #ffffff);
  color: var(--map-popup-fg, #1f1f1f);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
  border: 1px solid var(--map-popup-border, rgba(0, 0, 0, 0.08));
  font-family: inherit;
}

:deep(.map-popup .maplibregl-popup-tip) {
  display: none;
}

:deep(.map-popup .maplibregl-popup-close-button) {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
  color: var(--map-popup-muted, #6b7280);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
  transition:
    background 0.15s ease,
    color 0.15s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.06);
    color: var(--map-popup-fg, #1f1f1f);
  }
}

.v-theme--dark :deep(.map-popup .maplibregl-popup-close-button:hover) {
  background: rgba(255, 255, 255, 0.08);
}

:deep(.map-popup__body) {
  font-size: 13px;
  line-height: 1.45;
}

:deep(.map-popup__title) {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  padding-bottom: 6px;
  padding-right: 24px;
  border-bottom: 1px solid var(--map-popup-border, rgba(0, 0, 0, 0.08));
}

:deep(.map-popup__row) {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0;
}

:deep(.map-popup__label) {
  color: var(--map-popup-muted, #6b7280);
}

:deep(.map-popup__value) {
  font-weight: 500;
  text-align: right;
}

/* --- Тёмная тема --- */
.v-theme--dark {
  --map-popup-bg: #1f2228;
  --map-popup-fg: #eceff4;
  --map-popup-muted: #9aa3b2;
  --map-popup-border: rgba(255, 255, 255, 0.08);
}

.v-theme--dark :deep(.map-popup .maplibregl-popup-content) {
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
}

/* --- Маркеры --- */
:deep(.task-marker-shape) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--marker-color, #888);
  border: 2px solid #fff;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.v-theme--dark :deep(.task-marker-shape) {
  border-color: #1f2228;
}

:deep(.depot-marker-shape) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #444;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

:deep(.depot-marker-shape svg) {
  width: 16px;
  height: 16px;
  fill: #444;
}

.v-theme--dark :deep(.depot-marker-shape) {
  background: #1f2228;
  border-color: #eceff4;
}

.v-theme--dark :deep(.depot-marker-shape svg) {
  fill: #eceff4;
}
</style>
