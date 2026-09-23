<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl, { type Map as MapLibreMap, type Marker } from 'maplibre-gl'

import type {
  ApiResponse,
  Dataset,
  ExplanationResponse,
  EngineerRoute,
  ManualReassignmentPreview,
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
const explanationOpen = ref(false)
const explanationLoading = ref(false)
const explanationTaskId = ref('')
const explanationText = ref('')
const explanationTrace = ref<Record<string, unknown> | null>(null)
const explanationDeveloperMode = ref(false)
const reassignmentOpen = ref(false)
const reassignmentLoading = ref(false)
const reassignmentTaskId = ref('')
const reassignmentEngineerId = ref('')
const reassignmentPreview = ref<ManualReassignmentPreview | null>(null)
const reassignmentError = ref('')
// По умолчанию строим полностью новый план и не переносим исторические
// статусы из dataset в ограничения solver. Переключение ниже включает
// оперативный режим с сохранением уже начатых/назначенных заявок.
const ignoreTaskStatuses = ref(true)
const planningTime = ref('')
const createTaskOpen = ref(false)
const creatingTask = ref(false)
const geocodingTaskAddress = ref(false)
const taskAddressError = ref('')
const taskLocationMode = ref<'address' | 'map'>('address')
const selectingTaskPoint = ref(false)
const replanOpen = ref(false)
const replanning = ref(false)
const replanningEvent = ref({
  event_type: 'ENGINEER_UNAVAILABLE', planning_time: '12:00',
  engineer_id: '', task_id: '', emergency_id: '',
  latitude: null as number | null, longitude: null as number | null,
  duration_minutes: 80, window_start: '12:00', window_end: '14:00',
  required_vehicle_type: null as string | null, required_equipment: '',
})
const newTask = ref({
  id: '', address: '', latitude: null as number | null,
  longitude: null as number | null, work_type: 'LOCAL',
  window_start: '09:00', window_end: '11:00',
  priority: 'NORMAL', required_vehicle_type: null as string | null,
  required_equipment: '', status: 'NOT_SENT',
})

const WORK_NORMS: Record<string, { title: string; duration: number }> = {
  CONNECTION: { title: 'Подключение клиентов', duration: 70 },
  EMERGENCY: { title: 'Авария на ТКД', duration: 80 },
  EQUIPMENT_ORDER: { title: 'Дозаказ оборудования', duration: 20 },
  LOCAL: { title: 'Локальная заявка / ремонт', duration: 30 },
}

let map: MapLibreMap | null = null
let markers: Marker[] = []
let draftLocationMarker: Marker | null = null

const selectedWorkNorm = computed(() => WORK_NORMS[newTask.value.work_type])

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
  const engineersById = new Map(
    dataset.value?.engineers.map((engineer) => [engineer.id, engineer.name]) ?? [],
  )
  // Историческое назначение показываем только в статусном режиме. При полном
  // перераспределении старый current_engineer_id не должен выглядеть как
  // новое назначение, если solver оставил заявку без маршрута.
  dataset.value?.tasks.forEach((task) => {
    if (!ignoreTaskStatuses.value && task.current_engineer_id) {
      assignments[task.id] = engineersById.get(task.current_engineer_id) ?? task.current_engineer_id
    }
  })
  result.value?.routes.forEach((route) => {
    route.stops.forEach((stop) => {
      assignments[stop.task_id] = route.engineer_name
    })
  })
  return assignments
})

const formatNumber = (value: number, digits = 1) => value.toFixed(digits)

const plannableTaskCount = computed(
  () => dataset.value?.tasks.filter((task) => task.is_plannable).length ?? 0,
)

const STATUS_LABELS: Record<string, string> = {
  NOT_SENT: 'не отправлена',
  ASSIGNED: 'назначена',
  EN_ROUTE: 'в пути',
  IN_PROGRESS: 'в работе',
  COMPLETED: 'выполнена',
  CANCELLED: 'отменена',
  OVERDUE: 'просрочена',
}

function taskStatusLabel(task: Task): string {
  if (result.value && task.is_plannable) {
    if (assignedTaskIds.value.has(task.id)) {
      // Оперативный статус начатой заявки важнее факта её наличия в маршруте.
      if (['EN_ROUTE', 'IN_PROGRESS', 'OVERDUE'].includes(task.status)) {
        return STATUS_LABELS[task.status]
      }
      return 'назначена в плане'
    }
    return 'не назначена'
  }
  return STATUS_LABELS[task.status] ?? task.status
}

function taskStatusColor(task: Task): string {
  if (result.value && task.is_plannable && !assignedTaskIds.value.has(task.id)) return 'error'
  return {
    NOT_SENT: 'grey',
    ASSIGNED: 'indigo',
    EN_ROUTE: 'cyan-darken-1',
    IN_PROGRESS: 'blue-darken-1',
    COMPLETED: 'success',
    CANCELLED: 'grey-darken-1',
    OVERDUE: 'error',
  }[task.status] ?? 'grey'
}

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
    const response = await fetch('/api/optimize/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ignore_task_statuses: ignoreTaskStatuses.value,
        planning_time: !ignoreTaskStatuses.value && planningTime.value
          ? planningTime.value
          : null,
      }),
    })
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

async function createTask(): Promise<void> {
  creatingTask.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/tasks/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: newTask.value.id,
        address: newTask.value.address,
        latitude: newTask.value.latitude,
        longitude: newTask.value.longitude,
        work_type: newTask.value.work_type,
        window_start: newTask.value.window_start,
        window_end: newTask.value.window_end,
        priority: newTask.value.priority,
        required_vehicle_type: newTask.value.required_vehicle_type,
        status: newTask.value.status,
        required_equipment: newTask.value.required_equipment
          .split(',').map((item) => item.trim()).filter(Boolean),
      }),
    })
    const payload = await readResponse(response)
    dataset.value = payload.dataset
    result.value = null
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    createTaskOpen.value = false
    newTask.value = {
      id: '', address: '', latitude: null, longitude: null,
      work_type: 'LOCAL',
      window_start: '09:00', window_end: '11:00', priority: 'NORMAL',
      required_vehicle_type: null, required_equipment: '', status: 'NOT_SENT',
    }
    taskAddressError.value = ''
    draftLocationMarker?.remove()
    draftLocationMarker = null
    await refreshMap()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось создать заявку'
  } finally {
    creatingTask.value = false
  }
}

async function geocodeTaskAddress(): Promise<void> {
  if (!newTask.value.address.trim()) return
  geocodingTaskAddress.value = true
  taskAddressError.value = ''
  newTask.value.latitude = null
  newTask.value.longitude = null
  try {
    const response = await fetch('/api/geocode/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address: newTask.value.address }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error ?? 'Адрес не найден! Проверьте ввод.')
    newTask.value.latitude = payload.latitude
    newTask.value.longitude = payload.longitude
  } catch (error) {
    taskAddressError.value = error instanceof Error
      ? error.message
      : 'Адрес не найден! Проверьте ввод.'
  } finally {
    geocodingTaskAddress.value = false
  }
}

function changeTaskAddress(value: string): void {
  newTask.value.address = value
  newTask.value.latitude = null
  newTask.value.longitude = null
  taskAddressError.value = ''
}

function changeTaskLocationMode(mode: 'address' | 'map'): void {
  taskLocationMode.value = mode
  newTask.value.latitude = null
  newTask.value.longitude = null
  taskAddressError.value = ''
  draftLocationMarker?.remove()
  draftLocationMarker = null
}

function selectTaskPointOnMap(): void {
  if (!map) return
  selectingTaskPoint.value = true
  createTaskOpen.value = false
  map.getCanvas().style.cursor = 'crosshair'
  map.once('click', (event) => {
    newTask.value.longitude = event.lngLat.lng
    newTask.value.latitude = event.lngLat.lat
    newTask.value.address = ''
    taskAddressError.value = ''
    draftLocationMarker?.remove()
    draftLocationMarker = new maplibregl.Marker({ color: '#d32f2f' })
      .setLngLat(event.lngLat)
      .addTo(map as MapLibreMap)
    map!.getCanvas().style.cursor = ''
    selectingTaskPoint.value = false
    createTaskOpen.value = true
  })
}

async function replan(): Promise<void> {
  replanning.value = true
  errorMessage.value = ''
  try {
    const form = replanningEvent.value
    const payload: Record<string, unknown> = {
      event_type: form.event_type,
      planning_time: form.planning_time,
    }
    if (form.event_type === 'ENGINEER_UNAVAILABLE') payload.engineer_id = form.engineer_id
    if (form.event_type === 'TASK_CANCELLED') payload.task_id = form.task_id
    if (form.event_type === 'EMERGENCY_TASK') {
      payload.task = {
        id: form.emergency_id,
        latitude: form.latitude,
        longitude: form.longitude,
        work_type: 'EMERGENCY',
        window_start: form.window_start,
        window_end: form.window_end,
        priority: 'URGENT',
        required_vehicle_type: form.required_vehicle_type,
        required_equipment: form.required_equipment
          .split(',').map((item) => item.trim()).filter(Boolean),
        status: 'NOT_SENT',
      }
    }
    const response = await fetch('/api/replan/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const responsePayload = await readResponse(response)
    dataset.value = responsePayload.dataset
    result.value = responsePayload.result ?? null
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    replanOpen.value = false
    await refreshMap()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось перепланировать маршруты'
  } finally {
    replanning.value = false
  }
}

async function explainTask(taskId: string): Promise<void> {
  explanationLoading.value = true
  explanationTaskId.value = taskId
  explanationText.value = ''
  explanationTrace.value = null
  explanationDeveloperMode.value = false
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/explain/${encodeURIComponent(taskId)}/`, {
      method: 'POST',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error ?? 'Не удалось получить объяснение')
    const explanation = payload as ExplanationResponse
    explanationText.value = explanation.explanation
    explanationTrace.value = explanation.decision_trace ?? null
    explanationDeveloperMode.value = explanation.developer_mode
    explanationOpen.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : 'Не удалось получить объяснение'
  } finally {
    explanationLoading.value = false
  }
}

function openManualReassignment(taskId: string): void {
  reassignmentTaskId.value = taskId
  reassignmentEngineerId.value = ''
  reassignmentPreview.value = null
  reassignmentError.value = ''
  reassignmentOpen.value = true
}

async function previewManualReassignment(): Promise<void> {
  if (!reassignmentEngineerId.value) return
  reassignmentLoading.value = true
  reassignmentError.value = ''
  reassignmentPreview.value = null
  try {
    const response = await fetch('/api/manual-reassignment/preview/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: reassignmentTaskId.value,
        engineer_id: reassignmentEngineerId.value,
      }),
    })
    const payload = await response.json() as ManualReassignmentPreview & { error?: string }
    if (!response.ok) {
      reassignmentError.value = payload.message ?? payload.error ?? 'Переназначение невозможно.'
      return
    }
    reassignmentPreview.value = payload
  } catch (error) {
    reassignmentError.value = error instanceof Error ? error.message : 'Ошибка проверки переназначения.'
  } finally {
    reassignmentLoading.value = false
  }
}

async function confirmManualReassignment(): Promise<void> {
  const proposalId = reassignmentPreview.value?.proposal_id
  if (!proposalId) return
  reassignmentLoading.value = true
  reassignmentError.value = ''
  try {
    const response = await fetch('/api/manual-reassignment/confirm/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id: proposalId }),
    })
    const payload = await readResponse(response)
    dataset.value = payload.dataset
    result.value = payload.result ?? null
    reassignmentOpen.value = false
    selectedEngineerId.value = ''
    selectedEngineerIds.value = []
    await refreshMap()
  } catch (error) {
    reassignmentError.value = error instanceof Error ? error.message : 'Не удалось применить переназначение.'
  } finally {
    reassignmentLoading.value = false
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
        <v-snackbar v-model="selectingTaskPoint" :timeout="-1" color="primary" location="top">
          Нажмите на карту в месте новой заявки
        </v-snackbar>
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
            <v-btn color="primary" variant="tonal" :disabled="!dataset" @click="createTaskOpen = true">
              Создать заявку
            </v-btn>
            <v-btn color="warning" variant="tonal" :disabled="!dataset" @click="replanOpen = true">
              Перепланировать
            </v-btn>
            <v-switch
              v-model="ignoreTaskStatuses"
              label="Игнорировать статусы и перераспределить все заявки"
              color="primary"
              density="compact"
              hide-details
            />
            <v-text-field
              v-if="!ignoreTaskStatuses"
              v-model="planningTime"
              type="time"
              label="Текущее время"
              density="compact"
              hide-details
              style="max-width: 160px"
            />
            <span v-if="dataset" class="text-medium-emphasis">
              {{ dataset.source_name }} · {{ dataset.engineers.length }} инженеров ·
              {{ ignoreTaskStatuses ? dataset.tasks.length : plannableTaskCount }}
              в плане из {{ dataset.tasks.length }} заявок
            </span>
          </v-card-text>
        </v-card>

        <v-dialog v-model="createTaskOpen" max-width="760">
          <v-card>
            <v-card-title>Создать заявку</v-card-title>
            <v-card-text>
              <v-row dense>
                <v-col cols="12" sm="6"><v-text-field v-model="newTask.id" label="ID заявки *" /></v-col>
                <v-col cols="12" sm="6">
                  <v-select
                    v-model="newTask.work_type"
                    label="Тип работы *"
                    :items="Object.entries(WORK_NORMS).map(([value, norm]) => ({ title: norm.title, value }))"
                  />
                </v-col>
                <v-col cols="12" sm="6"><v-text-field :model-value="selectedWorkNorm.duration" readonly label="Норматив выполнения, минут" /></v-col>
                <v-col cols="12">
                  <v-btn-toggle :model-value="taskLocationMode" mandatory color="primary" @update:model-value="changeTaskLocationMode">
                    <v-btn value="address">Ввести адрес</v-btn>
                    <v-btn value="map">Поставить точку на карте</v-btn>
                  </v-btn-toggle>
                </v-col>
                <v-col v-if="taskLocationMode === 'address'" cols="12">
                  <v-text-field
                    :model-value="newTask.address"
                    label="Адрес клиента *"
                    :error-messages="taskAddressError"
                    hint="Введите адрес с номером дома и нажмите «Найти адрес»"
                    persistent-hint
                    @update:model-value="changeTaskAddress"
                    @keyup.enter="geocodeTaskAddress"
                  >
                    <template #append-inner>
                      <v-btn size="small" variant="text" :loading="geocodingTaskAddress" @click="geocodeTaskAddress">Найти адрес</v-btn>
                    </template>
                  </v-text-field>
                </v-col>
                <v-col v-else cols="12">
                  <v-btn color="primary" variant="outlined" @click="selectTaskPointOnMap">Выбрать точку на карте</v-btn>
                  <span class="ml-3 text-body-2">
                    {{ newTask.latitude === null ? 'Точка ещё не выбрана' : 'Точка выбрана' }}
                  </span>
                </v-col>
                <v-col cols="12" sm="6"><v-text-field :model-value="newTask.latitude ?? ''" readonly label="Широта (определяется автоматически)" /></v-col>
                <v-col cols="12" sm="6"><v-text-field :model-value="newTask.longitude ?? ''" readonly label="Долгота (определяется автоматически)" /></v-col>
                <v-col cols="12" sm="6"><v-text-field v-model="newTask.window_start" type="time" label="Начало окна, HH:MM (24 часа) *" /></v-col>
                <v-col cols="12" sm="6"><v-text-field v-model="newTask.window_end" type="time" label="Конец окна, HH:MM (24 часа) *" /></v-col>
                <v-col cols="12" sm="6"><v-select v-model="newTask.priority" label="Приоритет *" :items="['NORMAL', 'URGENT']" /></v-col>
                <v-col cols="12" sm="6">
                  <v-select v-model="newTask.required_vehicle_type" clearable label="Необходимый транспорт" :items="['CAR', 'WALK', 'BICYCLE', 'PUBLIC_TRANSPORT']" />
                </v-col>
                <v-col cols="12" sm="6"><v-select v-model="newTask.status" label="Статус" :items="['NOT_SENT', 'OVERDUE']" /></v-col>
                <v-col cols="12" sm="6"><v-text-field v-model="newTask.required_equipment" label="Оборудование через запятую" /></v-col>
              </v-row>
              <div class="text-caption text-medium-emphasis">Поля со звёздочкой обязательны. Новая заявка сохраняется в текущем локальном dataset.</div>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="createTaskOpen = false">Отмена</v-btn>
              <v-btn color="primary" :loading="creatingTask" :disabled="!newTask.id || newTask.latitude === null || newTask.longitude === null" @click="createTask">Создать</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <v-dialog v-model="replanOpen" max-width="720">
          <v-card>
            <v-card-title>Динамическое перепланирование</v-card-title>
            <v-card-text>
              <v-row dense>
                <v-col cols="12" sm="7">
                  <v-select
                    v-model="replanningEvent.event_type"
                    label="Событие"
                    :items="[
                      { title: 'Инженер стал недоступен', value: 'ENGINEER_UNAVAILABLE' },
                      { title: 'Поступила аварийная заявка', value: 'EMERGENCY_TASK' },
                      { title: 'Заявка отменена', value: 'TASK_CANCELLED' },
                    ]"
                  />
                </v-col>
                <v-col cols="12" sm="5"><v-text-field v-model="replanningEvent.planning_time" type="time" label="Текущее время *" /></v-col>
                <v-col v-if="replanningEvent.event_type === 'ENGINEER_UNAVAILABLE'" cols="12">
                  <v-select v-model="replanningEvent.engineer_id" label="Недоступный инженер *" :items="dataset?.engineers ?? []" item-title="name" item-value="id" />
                </v-col>
                <v-col v-if="replanningEvent.event_type === 'TASK_CANCELLED'" cols="12">
                  <v-select v-model="replanningEvent.task_id" label="Отменённая заявка *" :items="dataset?.tasks.filter((task) => !['CANCELLED', 'COMPLETED'].includes(task.status)) ?? []" item-title="id" item-value="id" />
                </v-col>
                <template v-if="replanningEvent.event_type === 'EMERGENCY_TASK'">
                  <v-col cols="12"><v-alert type="info" density="compact">Навык EMERGENCY_WORKS и приоритет URGENT устанавливаются автоматически.</v-alert></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model="replanningEvent.emergency_id" label="ID аварийной заявки *" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field model-value="80" readonly label="Норматив выполнения, минут" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model.number="replanningEvent.latitude" type="number" step="0.000001" label="Широта *" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model.number="replanningEvent.longitude" type="number" step="0.000001" label="Долгота *" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model="replanningEvent.window_start" type="time" label="Начало окна *" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model="replanningEvent.window_end" type="time" label="Конец окна *" /></v-col>
                  <v-col cols="12" sm="6"><v-select v-model="replanningEvent.required_vehicle_type" clearable label="Необходимый транспорт" :items="['CAR', 'WALK', 'BICYCLE', 'PUBLIC_TRANSPORT']" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field v-model="replanningEvent.required_equipment" label="Оборудование через запятую" /></v-col>
                </template>
              </v-row>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="replanOpen = false">Отмена</v-btn>
              <v-btn color="warning" :loading="replanning" @click="replan">Перестроить план</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

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
            <v-alert
              v-if="result && (result.metrics.reassigned_task_count || result.metrics.reordered_task_count)"
              type="info"
              variant="tonal"
              class="mb-2"
            >
              Изменения существующего плана: перенесено заявок —
              {{ result.metrics.reassigned_task_count }}, изменён порядок —
              {{ result.metrics.reordered_task_count }}, штраф стабильности —
              {{ result.metrics.plan_disruption_penalty }}.
            </v-alert>

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
                  <tr><th>#</th><th>Заявка</th><th>Прибытие</th><th>Работа</th><th>Пробег, км</th><th>Объяснение</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(stop, index) in selectedRoute.stops" :key="stop.task_id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ stop.task_id }}</td>
                    <td>{{ stop.arrival_time }}</td>
                    <td>{{ stop.service_start_time }}–{{ stop.service_end_time }}</td>
                    <td>{{ formatNumber(stop.distance_from_previous_km, 2) }}</td>
                    <td class="text-no-wrap explanation-action-cell">
                      <v-btn
                        size="small"
                        variant="outlined"
                        color="primary"
                        prepend-icon="mdi-chat-outline"
                        :loading="explanationLoading && explanationTaskId === stop.task_id"
                        :disabled="!result"
                        title="Показать причины назначения"
                        aria-label="Показать причины назначения"
                        @click="explainTask(stop.task_id)"
                      >
                        Причины
                      </v-btn>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>

            <v-card variant="outlined">
              <v-card-title>
                Заявки
                <span v-if="result" class="text-caption text-medium-emphasis ml-2">
                  Нажмите «Причины», чтобы получить объяснение назначения
                </span>
              </v-card-title>
              <v-table density="compact" fixed-header height="330">
                <thead>
                  <tr><th>ID / действия</th><th>Навык</th><th>Окно</th><th>Длительность</th><th>Исполнитель</th><th>Статус</th></tr>
                </thead>
                <tbody>
                  <tr v-for="task in dataset.tasks" :key="task.id">
                    <td class="text-no-wrap">
                      {{ task.id }}
                      <v-btn
                        size="x-small"
                        variant="outlined"
                        color="primary"
                        prepend-icon="mdi-chat-outline"
                        :loading="explanationLoading && explanationTaskId === task.id"
                        :disabled="!result || !task.is_plannable"
                        title="Показать причины назначения"
                        aria-label="Показать причины назначения"
                        @click="explainTask(task.id)"
                      >
                        Причины
                      </v-btn>
                      <v-btn
                        class="ml-1"
                        size="x-small"
                        variant="outlined"
                        color="secondary"
                        prepend-icon="mdi-account-switch-outline"
                        :disabled="!result || !task.is_plannable || (!ignoreTaskStatuses && ['CANCELLED', 'COMPLETED', 'EN_ROUTE', 'IN_PROGRESS'].includes(task.status))"
                        title="Переназначить заявку"
                        @click="openManualReassignment(task.id)"
                      >
                        Переназначить
                      </v-btn>
                    </td>
                    <td>{{ task.required_skill }}</td>
                    <td>{{ task.window_start }}–{{ task.window_end }}</td>
                    <td>{{ task.duration_minutes }} мин</td>
                    <td>{{ assignmentByTask[task.id] ?? '—' }}</td>
                    <td>
                      <v-chip size="x-small" :color="taskStatusColor(task)">
                        <v-icon v-if="task.assignment_locked" start size="x-small">mdi-lock</v-icon>
                        {{ taskStatusLabel(task) }}
                      </v-chip>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>

            <v-dialog v-model="explanationOpen" max-width="760">
              <v-card>
                <v-card-title>Причины назначения</v-card-title>
                <v-card-text>
                  <div class="explanation-text">{{ explanationText }}</div>
                  <details
                    v-if="explanationDeveloperMode && explanationTrace"
                    class="explanation-debug"
                  >
                    <summary>Показать JSON-проверки</summary>
                    <pre>{{ JSON.stringify(explanationTrace, null, 2) }}</pre>
                  </details>
                </v-card-text>
                <v-card-actions>
                  <v-spacer />
                  <v-btn variant="text" @click="explanationOpen = false">Закрыть</v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>

            <v-dialog v-model="reassignmentOpen" max-width="680">
              <v-card>
                <v-card-title>Ручное переназначение заявки {{ reassignmentTaskId }}</v-card-title>
                <v-card-text>
                  <v-select
                    v-model="reassignmentEngineerId"
                    :items="dataset.engineers"
                    item-title="name"
                    item-value="id"
                    label="Новый исполнитель"
                    :disabled="reassignmentLoading"
                    @update:model-value="reassignmentPreview = null; reassignmentError = ''"
                  />
                  <v-alert v-if="reassignmentError" type="error" variant="tonal" class="mb-3">
                    {{ reassignmentError }}
                  </v-alert>
                  <v-card v-if="reassignmentPreview?.feasible" variant="outlined">
                    <v-card-text>
                      <p>
                        <strong>{{ reassignmentPreview.old_engineer?.name ?? 'Не назначена' }}</strong>
                        → <strong>{{ reassignmentPreview.new_engineer?.name }}</strong>
                      </p>
                      <v-table density="compact" class="mt-3">
                        <thead><tr><th>Метрика</th><th>До</th><th>После</th></tr></thead>
                        <tbody>
                          <tr>
                            <td>Задействовано инженеров</td>
                            <td>{{ reassignmentPreview.before?.used_engineers_count }}</td>
                            <td>{{ reassignmentPreview.after?.used_engineers_count }}</td>
                          </tr>
                          <tr>
                            <td>Общий пробег</td>
                            <td>{{ formatNumber(reassignmentPreview.before?.total_distance_km ?? 0, 2) }} км</td>
                            <td>{{ formatNumber(reassignmentPreview.after?.total_distance_km ?? 0, 2) }} км</td>
                          </tr>
                        </tbody>
                      </v-table>
                      <v-alert type="warning" variant="tonal" class="mt-3">
                        План ещё не изменён. Проверьте показатели и подтвердите перенос.
                      </v-alert>
                    </v-card-text>
                  </v-card>
                </v-card-text>
                <v-card-actions>
                  <v-btn variant="text" @click="reassignmentOpen = false">Отмена</v-btn>
                  <v-spacer />
                  <v-btn
                    v-if="!reassignmentPreview?.feasible"
                    color="primary"
                    :loading="reassignmentLoading"
                    :disabled="!reassignmentEngineerId"
                    @click="previewManualReassignment"
                  >Проверить возможность</v-btn>
                  <v-btn
                    v-else
                    color="primary"
                    :loading="reassignmentLoading"
                    @click="confirmManualReassignment"
                  >Подтвердить переназначение</v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>
          </v-col>
        </v-row>
      </v-container>
    </v-main>
  </v-app>
</template>
