export const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/

export const isValidTime = (value: string): boolean => TIME_PATTERN.test(value)

export const timeToMinutes = (value: string): number => {
  const [h, m] = value.split(':').map(Number)
  return h! * 60 + m!
}
