import { useSyncExternalStore } from "react"

const MOBILE_BREAKPOINT = 768

const mql =
  typeof window !== "undefined"
    ? window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    : null

function subscribe(cb: () => void) {
  mql?.addEventListener("change", cb)
  return () => mql?.removeEventListener("change", cb)
}

function getSnapshot() {
  return mql ? mql.matches : false
}

function getServerSnapshot() {
  return false
}

export function useIsMobile() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
