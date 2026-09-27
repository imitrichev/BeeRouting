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
import { useDisplay } from 'vuetify/framework'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const display = useDisplay()
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
    center: [37.61, 55.617],
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
  element.innerHTML = `<span class="task-marker-shape"><span>${stopIndex ?? ''}</span></span>`
  return element
}

const getTaskMarkerWithPopup = (
  popupContent: string,
  longitude: number,
  latitude: number,
  color: string,
  stopIndex?: number,
): Marker => {
  const popup = new Popup({ offset: 25 }).setHTML(popupContent)
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
  return getTaskMarkerWithPopup(
    `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong>Заявка ${taskId}</strong><br/>
        <b>Тип:</b> ${getSkillTranslation(taskType)}<br/>
        <b>Длительность:</b> ${taskDuration} мин.<br/>
        <b>Окно:</b> ${taskWindowStart} - ${taskWindowEnd}<br/>
        <b>Приоритет:</b> ${getPriorityTranslation(taskPriority)}<br/>
      </div>
    `,
    taskLongitude,
    taskLatitude,
    color,
  )
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
  return getTaskMarkerWithPopup(
    `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong>Заявка ${taskId}</strong><br/>
        ${taskEngineerName ? `<b>Назначена:</b> ${taskEngineerName}<br/>` : ''}
        <b>Прибытие:</b> ${engineerArrival}<br/>
        <b>Работы:</b> ${engineerServiceStart} - ${engineerServiceEnd}<br/>
        <b>Время от пред. остановки:</b> ${engineerTravelTimeFromPrev} мин.<br/>
        <b>Дистанция от пред. остановки:</b> ${engineerDistanceFromPrev} км.<br/>
      </div>
    `,
    taskLongitude,
    taskLatitude,
    color,
    stopIndex,
  )
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
        new Popup({ offset: 16 }).setHTML(
          '<strong>Офис</strong><br>' + `${dataset.office_address ?? 'Адрес не указан'}`,
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
</script>

<template>
  <basic-card :loading="props.loading" title="Карта">
    <template #loading v-if="!firstLoadingComplete">
      <v-skeleton-loader type="article" />
    </template>
    <v-row no-gutters>
      <v-col v-if="isOptimized" class="border-right routes-col">
        <v-list
          class="overflow-list default-scrollbar py-1 pl-0 pr-2 map-container"
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
      </v-col>
      <v-col :cols="display.smAndDown.value ? 12 : undefined">
        <div v-if="firstLoadingComplete" ref="container" class="map-container" />
      </v-col>
    </v-row>
  </basic-card>
</template>

<style scoped lang="scss">
.map-container {
  width: 100% !important;
  min-height: 292px !important;
  height: calc(100vh - 500px) !important;
  max-height: 100vw !important;
}

.routes-col {
  width: fit-content !important;
  max-width: fit-content !important;
  @media (max-width: 839px) {
    width: 100% !important;
    max-width: 100% !important;
  }
}

.overflow-list {
  @media (max-width: 839px) {
    min-height: auto !important;
    max-height: 185px !important;
    border-bottom: 1px solid lightgray;
  }
}
</style>
