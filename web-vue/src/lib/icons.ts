import { addCollection } from '@iconify/vue'
import { localLucideIcons } from './localLucideIcons.generated'

let localIconsRegistered = false

export function registerLocalIcons() {
  if (localIconsRegistered) return

  addCollection(localLucideIcons)
  localIconsRegistered = true
}
