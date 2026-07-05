export interface MediaInfo {
  type: 'file' | 'url'
  uri: string
  title: string
  duration: number | null
  mime_type: string
  file_size: number | null
  thumbnail: string | null
}

export type MediaInputState = 'idle' | 'dragover' | 'input' | 'parsing' | 'ready'
