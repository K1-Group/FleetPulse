const KMH_TO_MPH = 0.621371

export function kmhToMph(speedKmh: number | null | undefined): number {
  const speed = Number(speedKmh ?? 0)
  if (!Number.isFinite(speed)) return 0
  return speed * KMH_TO_MPH
}

export function formatMph(speedKmh: number | null | undefined): string {
  return `${Math.round(kmhToMph(speedKmh))} mph`
}

export function roundedMph(speedKmh: number | null | undefined): number {
  return Math.round(kmhToMph(speedKmh))
}
