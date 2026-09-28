import type { Engineer } from '@/types/entities.ts'

export const getEngineerColor = (engineerId: string, engineers: Engineer[]): string => {
  const index = engineers.findIndex((e) => e.id === engineerId)
  if (index === -1) return '#CCC'
  // 30 разнообразных цветов, перемешаны в новом порядке
  const palette: string[] = [
    'hsl(280, 55%, 70%)', // лавандовый
    'hsl(0, 85%, 45%)', // насыщенный красный
    'hsl(185, 90%, 55%)', // яркая бирюза
    'hsl(40, 70%, 35%)', // тёмно-коричневый
    'hsl(250, 90%, 55%)', // яркий сине-фиолетовый
    'hsl(95, 80%, 40%)', // тёмно-лаймовый
    'hsl(345, 90%, 55%)', // ярко-малиновый
    'hsl(200, 60%, 75%)', // пастельный голубой
    'hsl(35, 95%, 45%)', // насыщенный оранжевый
    'hsl(105, 60%, 65%)', // светло-салатовый
    'hsl(330, 85%, 70%)', // светло-розовый
    'hsl(220, 95%, 35%)', // тёмно-синий
    'hsl(55, 95%, 55%)', // яркий жёлтый
    'hsl(170, 65%, 35%)', // тёмная бирюза
    'hsl(5, 80%, 65%)', // лососёвый
    'hsl(235, 80%, 65%)', // светло-индиго
    'hsl(65, 85%, 45%)', // оливково-жёлтый
    'hsl(315, 70%, 35%)', // тёмный пурпур
    'hsl(195, 95%, 65%)', // светло-циан
    'hsl(15, 90%, 40%)', // тёмно-оранжевый
    'hsl(140, 50%, 55%)', // приглушённый зелёный
    'hsl(300, 85%, 50%)', // яркая маджента
    'hsl(45, 100%, 70%)', // светло-золотой
    'hsl(210, 90%, 50%)', // яркий синий
    'hsl(80, 75%, 60%)', // жёлто-зелёный
    'hsl(175, 85%, 45%)', // морской
    'hsl(25, 95%, 60%)', // коралловый
    'hsl(155, 70%, 30%)', // тёмный изумруд
    'hsl(285, 90%, 45%)', // насыщенный фиолетовый
  ]

  return String(palette[index % palette.length])
}
export const hasFiniteCoordinates = (
  latitude: number | null | undefined,
  longitude: number | null | undefined,
): latitude is number => {
  return Number.isFinite(latitude) && Number.isFinite(longitude)
}
