export const getEngineerColor = (engineerId: string): string => {
  const hashString = (str: string): number => {
    let hash = 2166136248
    for (let i = 0; i < str.length; i++) {
      hash ^= str.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return hash >>> 0
  }
  const hash = hashString(engineerId)
  const hue = (hash * 0.61803398875 * 360) % 360

  const saturation = 60 + (hash % 3) * 10
  const lightness = 45 + ((hash >> 4) % 3) * 10

  return `hsl(${hue.toFixed(1)}, ${saturation}%, ${lightness}%)`
}

export const hasFiniteCoordinates = (
  latitude: number | null | undefined,
  longitude: number | null | undefined,
): latitude is number => {
  return Number.isFinite(latitude) && Number.isFinite(longitude)
}
