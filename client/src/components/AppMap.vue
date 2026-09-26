<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Map, Popup, Marker, NavigationControl, GeoJSONSource, LngLatBounds } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { getEngineerColor } from '@/utils/map.ts'
import { getPriorityTranslation, getSkillTranslation } from '@/utils/translations.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const tasks = computed(() => districtDataStore.getDistrictTasks)
const routes = computed(() => districtDataStore.getRoutes)
const isOptimized = computed(() => districtDataStore.isOptimized)
const selectedRoutes = computed(() => districtDataStore.selectedRoutes)
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
        paint: { 'line-color': '#ff0000', 'line-width': 4, 'line-opacity': 0.8 },
      })
    }

    // 2) потом маркеры + данные
    if (isOptimized.value) renderRoutes()
    else renderTasks()
  })
}

const getTaskMarker = (
  popupContent: string,
  longitude: number,
  latitude: number,
  color: string,
): Marker => {
  const popup = new Popup({ offset: 25 }).setHTML(popupContent)
  return new Marker({ color }).setLngLat([longitude, latitude]).setPopup(popup).addTo(map!)
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
  return getTaskMarker(
    `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong>Задача ${taskId}</strong><br/>
        <b>Тип:</b> ${getSkillTranslation(taskType)}<br/>
        <b>Длительность:</b> ${taskDuration} мин.<br/>
        <b>Окно:</b> ${taskWindowStart} — ${taskWindowEnd}<br/>
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
): Marker => {
  return getTaskMarker(
    `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong>Задача ${taskId}</strong><br/>
        ${taskEngineerName ? `<b>Назначена:</b> ${taskEngineerName}<br/>` : ''}
        <b>Прибытие:</b> ${engineerArrival}<br/>
        <b>Работы:</b> ${engineerServiceStart} — ${engineerServiceEnd}<br/>
        <b>Время от пред. остановки:</b> ${engineerTravelTimeFromPrev} мин.<br/>
        <b>Дистанция от пред. остановки:</b> ${engineerDistanceFromPrev} км.<br/>
      </div>
    `,
    taskLongitude,
    taskLatitude,
    color,
  )
}

const clearMarkers = () => {
  markers.forEach((marker) => marker.remove())
  markers = []
}

const renderRouteLines = () => {
  if (!map || !isOptimized.value) {
    console.warn('skip: map?', !!map, 'isOptimized?', isOptimized.value)
    return
  }

  const source = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
  if (!source) {
    console.warn('source not found')
    return
  }

  const features = routes.value
    .filter((r) => r.geometry && r.geometry.coordinates.length >= 2)
    .map((route) => ({
      type: 'Feature' as const,
      properties: {
        color: getEngineerColor(route.engineer_id),
        engineer_id: route.engineer_id,
        engineer_name: route.engineer_name,
      },
      geometry: {
        type: 'LineString' as const,
        coordinates: route.geometry!.coordinates as [number, number][],
      },
    }))

  const bounds = new LngLatBounds()
  features.forEach((f) => f.geometry.coordinates.forEach((c) => bounds.extend(c)))
  map.fitBounds(bounds, { padding: 40 })

  source.setData({ type: 'FeatureCollection', features })
}

const renderRoutes = () => {
  if (!map || !isOptimized.value) return

  clearMarkers()

  routes.value.forEach((route) => {
    const color = selectedRoutes.value.includes(route.engineer_id)
      ? getEngineerColor(route.engineer_id)
      : '#888888'

    route.stops.forEach((stop, index) => {
      if (stop.longitude === null || stop.latitude === null) return

      markers.push(
        getOptimizedMarker(
          color,
          stop.task_id,
          `${route.engineer_name} (#${index + 1})`,
          stop.arrival_time,
          stop.service_start_time,
          stop.service_end_time,
          stop.travel_time_from_previous,
          stop.distance_from_previous_km.toFixed(2),
          stop.longitude,
          stop.latitude,
        ),
      )
    })
  })

  renderRouteLines()
}

const renderTasks = () => {
  if (!map || isOptimized.value) return

  clearMarkers()

  tasks.value.forEach((task) => {
    if (task.latitude === null || task.longitude === null) return

    markers.push(
      getNotOptimizedMarker(
        '#888888',
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
  })
}

watch(
  () => props.loading,
  async (nVal) => {
    if (nVal) return
    firstLoadingComplete.value = true
    await nextTick()
    renderMap()
  },
)

watch(() => [...selectedRoutes.value], renderRoutes)

watch(isOptimized, (val) => {
  if (!map) return
  if (val) {
    renderRoutes()
  } else {
    const source = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
    source?.setData({ type: 'FeatureCollection', features: [] })
    clearMarkers()
    renderTasks()
  }
})

onBeforeUnmount(() => {
  clearMarkers()
  map?.remove()
  map = null
})
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading v-if="!firstLoadingComplete">
      <v-skeleton-loader type="article" />
    </template>
    <div v-if="firstLoadingComplete" ref="container" class="map-container" />
  </basic-card>
</template>

<style scoped lang="scss">
.map-container {
  width: 100% !important;
  height: calc(100vh - 66px - 24px - 110px) !important;
  min-height: 292px !important;
}
</style>
