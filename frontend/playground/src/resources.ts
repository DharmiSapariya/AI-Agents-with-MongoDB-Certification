import { useEffect, useState } from 'react'
import { ApiError, errorText, json } from './api'

export type Access = { token: string; onExpired: () => void }

export function useResource<T>(path: string | null, { token, onExpired }: Access) {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{ path: string; data?: T; error?: string }>()
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    json<T>(path, { signal: controller.signal }, token).then(data => {
      if (!controller.signal.aborted) setState({ path, data })
    }).catch(error => {
      if (controller.signal.aborted) return
      if (error instanceof ApiError && error.status === 401) onExpired()
      else setState({ path, error: errorText(error) })
    })
    return () => controller.abort()
  }, [path, token, onExpired, revision])
  return {
    ...(state?.path === path ? state : undefined),
    reload: () => setRevision(value => value + 1),
  }
}
