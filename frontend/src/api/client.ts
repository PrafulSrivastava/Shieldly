import { useStore } from '../store'

const BASE = 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const { token, adminKey } = useStore.getState()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (adminKey) headers['X-Admin-Key'] = adminKey
  if (extraHeaders) Object.assign(headers, extraHeaders)

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (res.status === 204) return undefined as T

  const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail ?? `HTTP ${res.status}`)
  }

  return data as T
}

export const get = <T>(path: string, headers?: Record<string, string>) =>
  request<T>('GET', path, undefined, headers)

export const post = <T>(path: string, body?: unknown) =>
  request<T>('POST', path, body)

export const patch = <T>(path: string, body?: unknown) =>
  request<T>('PATCH', path, body)
