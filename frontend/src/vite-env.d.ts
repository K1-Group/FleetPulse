/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_ACCESS_PREVIEW_ADMIN_EMAILS?: string
  readonly VITE_ACCESS_PREVIEW_ENABLED?: string
  readonly VITE_ACCESS_PREVIEW_USERS_JSON?: string
  readonly DEV: boolean
  readonly PROD: boolean
  readonly SSR: boolean
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
