<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Map, Marker, NavigationControl, Popup } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useCurrentStateStore } from '@/stores/state.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const stateStore = useCurrentStateStore()

let map: Map | null = null
let markers: Marker[] = []

const container = ref<HTMLElement | null>(null)

const tasks = computed(() => stateStore.getTasks)

const renderMap = () => {
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
}

const renderTasks = () => {
  if (!map) return

  markers.forEach((marker) => marker.remove())
  markers = []

  tasks.value.forEach((task) => {
    if (task.latitude === null || task.longitude === null) return

    const popupContent = `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong>Task ${task.id}</strong><br/>
        <b>Skill:</b> ${task.required_skill}<br/>
        <b>Duration:</b> ${task.duration_minutes} min<br/>
        <b>Window:</b> ${new Date(task.window_start).toLocaleString()} — ${new Date(task.window_end).toLocaleString()}<br/>
        <b>Priority:</b> ${task.priority}<br/>
        ${task.required_vehicle_type ? `<b>Vehicle:</b> ${task.required_vehicle_type}<br/>` : ''}
      </div>
    `

    const popup = new Popup({ offset: 25 }).setHTML(popupContent)

    const marker = new Marker({ color: '#888888' })
      .setLngLat([task.longitude, task.latitude])
      .setPopup(popup)
      .addTo(map!)

    markers.push(marker)
  })
}

watch(
  () => props.loading,
  (nVal) => {
    if (nVal) return

    nextTick(() => {
      renderMap()
      nextTick(() => {
        renderTasks()
      })
    })
  },
)

watch(tasks, () => {
  if (map) renderTasks()
})

onBeforeUnmount(() => {
  markers.forEach((m) => m.remove())
  markers = []
  map?.remove()
  map = null
})
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="article" />
    </template>
    <div ref="container" class="map-container" />
  </basic-card>
</template>

<style scoped lang="scss">
.map-container {
  height: calc(100vh - 66px - 24px - 100px) !important;
  min-height: 292px !important;
  min-width: unset !important;
  width: unset !important;
  @media (max-width: 839px) {
    height: min(100vh - 66px - 24px - 100px, 100vw) !important;
  }
}
</style>
