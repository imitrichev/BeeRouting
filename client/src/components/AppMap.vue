<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { nextTick, ref, watch } from 'vue'
import { type Map as MapLibreMap, Map, NavigationControl } from 'maplibre-gl'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

let map: MapLibreMap | null = null
const container = ref<HTMLElement | null>(null)

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
  map.addControl(new NavigationControl(), 'top-right')
  map.on('load', () => {
    map?.addSource('routes', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
    map?.addLayer({
      id: 'route-lines',
      type: 'line',
      source: 'routes',
      // Цвет берётся из свойства каждой GeoJSON-линии, поэтому несколько
      // выбранных инженеров видны одновременно и не смешиваются.
      paint: { 'line-color': ['get', 'color'], 'line-width': 5, 'line-opacity': 0.9 },
    })
    map?.resize()
  })
}

watch(
  () => props.loading,
  (nVal) => {
    if (nVal) return

    nextTick(() => {
      renderMap()
    })
  },
)
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
