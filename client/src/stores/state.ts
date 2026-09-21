import { defineStore } from 'pinia'
import type { Engineer, OptimizationResult, Task } from '@/types/entities.ts'
import { computed, ref } from 'vue'

export const useCurrentStateStore = defineStore('currentState', () => {
  const optimizationResult = ref<OptimizationResult | null>(null)

  const tasks = ref<Task[]>([])
  const engineers = ref<Engineer[]>([])

  const sourceName = ref<string | null>('')
  const scenarioName = ref<string>('')

  const expandedTaskIds = ref<string[]>([])
  const expandedEngineerIds = ref<string[]>([])

  const selectedTaskIds = ref<string[]>([])
  const selectedEngineerIds = ref<string[]>([])

  const getTasks = computed(() => tasks.value)
  const getEngineers = computed(() => engineers.value)
  const getSourceName = computed(() => sourceName.value)
  const getScenarioName = computed(() => scenarioName.value)

  const getExpandedTaskIds = computed(() => expandedTaskIds.value)
  const getExpandedEngineerIds = computed(() => expandedEngineerIds.value)

  const getSelectedTaskIds = computed(() => selectedTaskIds.value)
  const getSelectedEngineerIds = computed(() => selectedEngineerIds.value)

  const getOptimizationResult = computed(() => optimizationResult.value)

  const setTasks = (items: Task[]) => {
    tasks.value = [...items]
  }

  const setEngineers = (items: Engineer[]) => {
    engineers.value = [...items]
  }

  const setSourceName = (name: string | null) => {
    sourceName.value = name
  }

  const setScenarioName = (name: string) => {
    scenarioName.value = name
  }

  const setExpandedTaskIds = (ids: string[]) => {
    expandedTaskIds.value = [...ids]
  }

  const setExpandedEngineerIds = (ids: string[]) => {
    expandedEngineerIds.value = [...ids]
  }

  const setSelectedTaskIds = (ids: string[]) => {
    selectedTaskIds.value = [...ids]
  }

  const setSelectedEngineerIds = (ids: string[]) => {
    selectedEngineerIds.value = [...ids]
  }

  const toggleExpandedTask = (id: string) => {
    const idx = expandedTaskIds.value.indexOf(id)
    if (idx === -1) expandedTaskIds.value.push(id)
    else expandedTaskIds.value.splice(idx, 1)
  }

  const toggleExpandedEngineer = (id: string) => {
    const idx = expandedEngineerIds.value.indexOf(id)
    if (idx === -1) expandedEngineerIds.value.push(id)
    else expandedEngineerIds.value.splice(idx, 1)
  }

  const setOptimizationResult = (result: OptimizationResult | null) => {
    optimizationResult.value = result
  }

  return {
    getTasks,
    getEngineers,
    getSourceName,
    getScenarioName,
    getExpandedTaskIds,
    getExpandedEngineerIds,
    getSelectedTaskIds,
    getSelectedEngineerIds,
    setTasks,
    setEngineers,
    setSourceName,
    setScenarioName,
    setExpandedTaskIds,
    setExpandedEngineerIds,
    setSelectedTaskIds,
    setSelectedEngineerIds,
    toggleExpandedTask,
    toggleExpandedEngineer,
    getOptimizationResult,
    setOptimizationResult,
  }
})
