<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl, { type Map as MapLibreMap, type Marker } from 'maplibre-gl'

import type {
  ApiResponse,
  Dataset,
  EngineerRoute,
  OptimizationResult,
  Task,
} from './types'

const dataset = ref<Dataset | null>(null)
const result = ref<OptimizationResult | null>(null)
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const optimizing = ref(false)
const errorMessage = ref('')
const selectedEngineerId = ref('')
const selectedEngineerIds = ref<string[]>([])
const mapContainer = ref<HTMLElement | null>(null)

let map: MapLibreMap | null = null
let markers: Marker[] = []

const selectedRoute = computed<EngineerRoute | null>(() => {
  if (!result.value || !selectedEngineerId.value) return null
  return result.value.routes.find(
    (route) => route.engineer_id === selectedEngineerId.value,
  ) ?? null
})

function setEngineerSelection(engineerId: string, selected: boolean): void {
  if (selected) {
    if (!selectedEngineerIds.value.includes(engineerId)) {
      selectedEngineerIds.value = [...selectedEngineerIds.value, engineerId]
    }
    // Показываем таблицу маршрута последнего отмеченного инженера.
    selectedEngineerId.value = engineerId
    return
  }

  selectedEngineerIds.value = selectedEngineerIds.value.filter(
    (id) => id !== engineerId,
  )
  if (selectedEngineerId.value === engineerId) {
    selectedEngineerId.value = selectedEngineerIds.value[0] ?? ''
  }
}

// Палитра рассчитана максимум на 15 инженеров из ТЗ. Цвет закрепляется за
// позицией инженера в dataset, поэтому не меняется при построении маршрута.
// Оттенки намеренно достаточно контрастны, чтобы маршруты можно было
// различать и на карте, и в списке инженеров.
const ENGINEER_COLORS = [
  '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
  '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
  '#008080', '#e6beff', '#9a6324', '#800000', '#aaffc3',
]

function engineerColor(engineerId: string): string {
  const index = dataset.value?.engineers.findIndex(
    (engineer) => engineer.id === engineerId,
  ) ?? -1
  return index >= 0 ? ENGINEER_COLORS[index % ENGINEER_COLORS.length] : '#757575'
}

// MapLibre поддерживает собственный HTMLElement через Marker({ element }).
// Используем его, чтобы номер остановки был частью самой геометки.
function createTaskMarkerElement(
  orderNumber: number | undefined,
  color: string,
): HTMLElement {
  const element = document.createElement('div')
  element.className = 'task-marker'
  element.style.setProperty('--marker-color', color)
  element.setAttribute(
    'aria-label',
    orderNumber ? `Остановка ${orderNumber}` : 'Заявка',
  )
  element.innerHTML = `<span class="task-marker-shape"><span>${orderNumber ?? ''}</span></span>`
  return element
}

// Домик показывает общее депо, откуда начинаются маршруты инженеров.
function createDepotMarkerElement(): HTMLElement {
  const element = document.createElement('div')
  element.className = 'depot-marker'
  element.setAttribute('aria-label', 'Депо')
  element.innerHTML = `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 10.5 12 3l9 7.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19.5v-9Z" />
      <path class="depot-door" d="M9 21v-6h6v6" />
    </svg>
  `
  return element
}

const assignedTaskIds = computed(() => {
  const ids = new Set<string>()
  result.value?.routes.forEach((route) => {
    route.stops.forEach((stop) => ids.add(stop.task_id))
  })
  return ids
})

const assignmentByTask = computed(() => {
  const assignments: Record<string, string> = {}
  result.value?.routes.forEach((route) => {
    route.stops.forEach((stop) => {
      assignments[stop.task_id] = route.engineer_name
    })
  })
  return assignments
})

const formatNumber = (value: number, digits = 1) => value.toFixed(digits)

async function readResponse(response: Response): Promise<ApiResponse> {
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.error ?? 'Ошибка API')
  return payload as ApiResponse
}

async function loadOfficialDataset() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/dataset/official/')
    const payload = await readResponse(response)
    dataset.value = payload.dataset
    result.value = null
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    await refreshMap()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить dataset'
  } finally {
    loading.value = false
  }
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function uploadDataset() {
  if (!selectedFile.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const response = await fetch('/api/dataset/upload/', {
      method: 'POST',
      body: formData,
    })
    const payload = await readResponse(response)
    dataset.value = payload.dataset
    result.value = null
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    await refreshMap()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить dataset'
  } finally {
    loading.value = false
  }
}

async function optimize() {
  optimizing.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/optimize/', { method: 'POST' })
    const payload = await readResponse(response)
    dataset.value = payload.dataset
    result.value = payload.result ?? null
    // После расчёта не выбираем инженера автоматически: все заявки должны
    // остаться серыми, пока диспетчер сам не откроет нужный маршрут.
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    await refreshMap()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось запустить оптимизацию'
  } finally {
    optimizing.value = false
  }
}

function routeCoordinates(route: EngineerRoute): [number, number][] {
  const coordinates: [number, number][] = []
  if (route.start_longitude !== null && route.start_latitude !== null) {
    coordinates.push([route.start_longitude, route.start_latitude])
  }
  route.stops.forEach((stop) => {
    if (stop.longitude !== null && stop.latitude !== null) {
      coordinates.push([stop.longitude, stop.latitude])
    }
  })
  return coordinates
}

function drawMap() {
  if (!map) return
  markers.forEach((marker) => marker.remove())
  markers = []

  const allRoutes = result.value?.routes ?? []
  // Галочки управляют именно видимостью на карте. Можно одновременно
  // выбрать несколько инженеров и увидеть их линии разными цветами.
  const routes = allRoutes.filter((route) =>
    selectedEngineerIds.value.includes(route.engineer_id),
  )
  const activeRouteByTask = new globalThis.Map(
    routes.flatMap((route) =>
      route.stops.map((stop) => [stop.task_id, route] as const),
    ),
  )
  const assignedRouteByTask = new globalThis.Map(
    allRoutes.flatMap((route) =>
      route.stops.map((stop) => [stop.task_id, route] as const),
    ),
  )
  const orderByTask = new globalThis.Map(
    routes.flatMap((route) =>
      route.stops.map((stop, index) => [stop.task_id, index + 1] as const),
    ),
  )
  const features = routes
    .map((route) => {
      // OSRM возвращает дорожную линию в GeoJSON. Если внешний provider не
      // дал geometry, оставляем прямые отрезки между точками как fallback.
      const coordinates = route.geometry?.type === 'LineString'
        ? route.geometry.coordinates as [number, number][]
        : routeCoordinates(route)
      return coordinates.length < 2
        ? null
        : {
            type: 'Feature',
            properties: {
              engineer_id: route.engineer_id,
              color: engineerColor(route.engineer_id),
            },
            geometry: { type: 'LineString', coordinates },
          }
    })
    .filter(Boolean)

  const sourceData = {
    type: 'FeatureCollection',
    features,
  }
  const source = map.getSource('routes') as maplibregl.GeoJSONSource | undefined
  if (source) source.setData(sourceData as never)

  // Общая начальная точка всех маршрутов обозначается домиком.
  const depotEngineer = dataset.value?.engineers.find(
    (engineer) => engineer.start_longitude !== null && engineer.start_latitude !== null,
  )
  if (
    depotEngineer &&
    depotEngineer.start_longitude !== null &&
    depotEngineer.start_latitude !== null
  ) {
    const depotMarker = new maplibregl.Marker({
      element: createDepotMarkerElement(),
      anchor: 'bottom',
    })
      .setLngLat([depotEngineer.start_longitude, depotEngineer.start_latitude])
      .setPopup(new maplibregl.Popup({ offset: 16 }).setText('Депо'))
      .addTo(map as MapLibreMap)
    markers.push(depotMarker)
  }

  // Заявки показываются уже после загрузки dataset. После выбора инженера
  // только его маркеры получают цвет и номер остановки.
  dataset.value?.tasks.forEach((task) => {
    if (task.longitude === null || task.latitude === null) return
    const route = activeRouteByTask.get(task.id)
    const assignedRoute = assignedRouteByTask.get(task.id)
    const marker = new maplibregl.Marker({
      // После расчёта route содержит только выбранного инженера, поэтому
      // заявки остальных инженеров и неназначенные заявки остаются серыми.
      element: createTaskMarkerElement(
        orderByTask.get(task.id),
        route ? engineerColor(route.engineer_id) : '#757575',
      ),
      anchor: 'bottom',
    })
      .setLngLat([task.longitude, task.latitude])
      .setPopup(
        new maplibregl.Popup({ offset: 16 }).setHTML(
          `<strong>${task.id}</strong><br>` +
            `${assignedRoute ? assignedRoute.engineer_name : 'Пока не назначена'}<br>` +
            `${task.window_start}–${task.window_end}<br>` +
            `${task.duration_minutes} мин`,
        ),
      )
      .addTo(map as MapLibreMap)
    markers.push(marker)
  })

  const allCoordinates = [
    ...(dataset.value?.tasks ?? [])
      .filter((task) => task.longitude !== null && task.latitude !== null)
      .map((task) => [task.longitude as number, task.latitude as number] as [number, number]),
    ...(dataset.value?.engineers ?? [])
      .filter((engineer) => engineer.start_longitude !== null && engineer.start_latitude !== null)
      .map((engineer) => [engineer.start_longitude as number, engineer.start_latitude as number] as [number, number]),
  ]
  if (allCoordinates.length > 0) {
    const bounds = allCoordinates.reduce(
      (currentBounds, coordinate) => currentBounds.extend(coordinate),
      new maplibregl.LngLatBounds(allCoordinates[0], allCoordinates[0]),
    )
    map.fitBounds(bounds, { padding: 40, maxZoom: 12 })
  }
}

function createMap() {
  if (!mapContainer.value) return
  map = new maplibregl.Map({
    container: mapContainer.value,
    // Для понятной проверки MVP используем публичную raster-подложку OSM.
    // OSRM по-прежнему отвечает только за дорожные матрицы и geometry маршрутов.
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
  map.addControl(new maplibregl.NavigationControl(), 'top-right')
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
    drawMap()
  })
}

async function refreshMap() {
  // Блок карты находится внутри v-if="dataset". До завершения загрузки
  // dataset контейнера ещё нет в DOM, поэтому попытка создать карту из
  // первоначального onMounted была слишком ранней.
  await nextTick()
  if (!map && mapContainer.value) {
    createMap()
    return
  }
  map?.resize()
  drawMap()
}

onMounted(() => {
  loadOfficialDataset()
})

// Срабатывает после появления/замены dataset и гарантирует, что ref карты
// уже указывает на реальный DOM-элемент.
watch(dataset, () => {
  void refreshMap()
})

// Выбор инженера в списке одновременно обновляет серые/цветные маркеры и
// единственную видимую линию его маршрута.
watch(selectedEngineerId, () => {
  void refreshMap()
})

// Изменение галочки сразу пересобирает набор цветных маркеров и линий.
watch(selectedEngineerIds, () => {
  void refreshMap()
})

onBeforeUnmount(() => {
  markers.forEach((marker) => marker.remove())
  map?.remove()
})
</script>

<template>
  <v-app>
    <v-app-bar color="primary" density="comfortable">
      <v-app-bar-title>BeeRouting · Optimization MVP</v-app-bar-title>
    </v-app-bar>

    <v-main>
      <v-container fluid class="pa-4">
        <v-alert v-if="errorMessage" type="error" closable class="mb-4" @click:close="errorMessage = ''">
          {{ errorMessage }}
        </v-alert>

        <v-card class="mb-4" variant="outlined">
          <v-card-text class="d-flex flex-wrap align-center ga-3">
            <v-btn color="primary" :loading="loading" @click="loadOfficialDataset">
              Открыть официальный dataset
            </v-btn>
            <v-file-input
              accept="application/json,.json"
              label="JSON dataset"
              density="compact"
              hide-details
              class="file-input"
              @change="onFileSelected"
            />
            <v-btn variant="tonal" :disabled="!selectedFile" :loading="loading" @click="uploadDataset">
              Загрузить JSON
            </v-btn>
            <v-btn color="success" :loading="optimizing" :disabled="!dataset" @click="optimize">
              Запустить OR-Tools
            </v-btn>
            <span v-if="dataset" class="text-medium-emphasis">
              {{ dataset.source_name }} · {{ dataset.engineers.length }} инженеров · {{ dataset.tasks.length }} заявок
            </span>
          </v-card-text>
        </v-card>

        <v-row v-if="dataset">
          <v-col cols="12" md="4" lg="3">
            <v-card variant="outlined" class="mb-4">
              <v-card-title>Инженеры</v-card-title>
              <v-card-subtitle>Отметьте инженеров для показа маршрутов на карте</v-card-subtitle>
              <v-list density="compact">
                <v-list-item
                  v-for="engineer in dataset.engineers"
                  :key="engineer.id"
                  :active="selectedEngineerId === engineer.id"
                  @click="selectedEngineerId = engineer.id"
                >
                  <template #prepend>
                    <v-checkbox
                      :model-value="selectedEngineerIds.includes(engineer.id)"
                      :color="engineerColor(engineer.id)"
                      density="compact"
                      hide-details
                      class="engineer-checkbox"
                      @click.stop
                      @update:model-value="setEngineerSelection(engineer.id, Boolean($event))"
                    />
                    <span
                      class="engineer-color-dot"
                      :style="{ backgroundColor: engineerColor(engineer.id) }"
                    />
                  </template>
                  <v-list-item-title>{{ engineer.name }}</v-list-item-title>
                  <v-list-item-subtitle>
                    {{ engineer.vehicle_type }} · {{ engineer.available_from }}–{{ engineer.available_until }}
                    <span v-if="result"> · {{ result.routes.find((route) => route.engineer_id === engineer.id)?.stops.length ?? 0 }} заявок</span>
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-card>

            <v-card v-if="result" variant="outlined">
              <v-card-title>Unassigned заявки</v-card-title>
              <v-card-text v-if="!result.unassigned.length" class="text-success">
                Все заявки назначены
              </v-card-text>
              <v-list v-else density="compact">
                <v-list-item v-for="item in result.unassigned" :key="item.task_id">
                  <v-list-item-title>{{ item.task_id }}</v-list-item-title>
                  <v-list-item-subtitle>{{ item.message }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-card>
          </v-col>

          <v-col cols="12" md="8" lg="9">
            <v-row v-if="result" dense class="mb-2">
              <v-col cols="6" sm="3">
                <v-card color="blue-lighten-5" variant="flat"><v-card-text><div class="metric-label">Задействовано</div><strong>{{ result.metrics.used_engineers_count }}</strong></v-card-text></v-card>
              </v-col>
              <v-col cols="6" sm="3">
                <v-card color="green-lighten-5" variant="flat"><v-card-text><div class="metric-label">Назначено</div><strong>{{ result.metrics.assigned_task_count }}</strong></v-card-text></v-card>
              </v-col>
              <v-col cols="6" sm="3">
                <v-card color="orange-lighten-5" variant="flat"><v-card-text><div class="metric-label">Пробег, км</div><strong>{{ formatNumber(result.metrics.total_distance_km) }}</strong></v-card-text></v-card>
              </v-col>
              <v-col cols="6" sm="3">
                <v-card color="purple-lighten-5" variant="flat"><v-card-text><div class="metric-label">Objective</div><strong>{{ result.metrics.total_objective }}</strong></v-card-text></v-card>
              </v-col>
            </v-row>

            <v-card variant="outlined" class="map-card mb-4">
              <v-card-title>
                Карта маршрутов
                <span v-if="selectedRoute" class="text-caption text-medium-emphasis ml-2">
                  {{ selectedRoute.engineer_name }} · {{ selectedRoute.stops.length }} заявок
                </span>
              </v-card-title>
              <div ref="mapContainer" class="map-container" />
            </v-card>

            <v-card v-if="selectedRoute" variant="outlined" class="mb-4">
              <v-card-title>Маршрут выбранного инженера</v-card-title>
              <v-table density="compact">
                <thead>
                  <tr><th>#</th><th>Заявка</th><th>Прибытие</th><th>Работа</th><th>Пробег, км</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(stop, index) in selectedRoute.stops" :key="stop.task_id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ stop.task_id }}</td>
                    <td>{{ stop.arrival_time }}</td>
                    <td>{{ stop.service_start_time }}–{{ stop.service_end_time }}</td>
                    <td>{{ formatNumber(stop.distance_from_previous_km, 2) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>

            <v-card variant="outlined">
              <v-card-title>Заявки</v-card-title>
              <v-table density="compact" fixed-header height="330">
                <thead>
                  <tr><th>ID</th><th>Навык</th><th>Окно</th><th>Длительность</th><th>Исполнитель</th><th>Статус</th></tr>
                </thead>
                <tbody>
                  <tr v-for="task in dataset.tasks" :key="task.id">
                    <td>{{ task.id }}</td>
                    <td>{{ task.required_skill }}</td>
                    <td>{{ task.window_start }}–{{ task.window_end }}</td>
                    <td>{{ task.duration_minutes }} мин</td>
                    <td>{{ assignmentByTask[task.id] ?? '—' }}</td>
                    <td>
                      <v-chip v-if="assignedTaskIds.has(task.id)" size="x-small" color="success">назначена</v-chip>
                      <v-chip v-else-if="result" size="x-small" color="error">не назначена</v-chip>
                      <v-chip v-else size="x-small" color="grey">ожидает</v-chip>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </v-col>
        </v-row>
      </v-container>
    </v-main>
  </v-app>
</template>
