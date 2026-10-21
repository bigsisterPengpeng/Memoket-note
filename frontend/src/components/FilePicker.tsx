import { useRef } from 'react'

export default function FilePicker({ label, accept, directory = false, multiple = false, disabled = false, disabledReason, onPick }: {
  label: string
  accept?: string
  directory?: boolean
  multiple?: boolean
  disabled?: boolean
  disabledReason: string
  onPick: (files: FileList) => void
}) {
  const input = useRef<HTMLInputElement | null>(null)
  return <>
    <button type="button" disabled={disabled} title={disabled ? disabledReason : undefined}
      onClick={() => input.current?.click()}>{label}</button>
    <input hidden type="file" accept={accept} multiple={multiple} disabled={disabled} aria-label={label}
      ref={(element) => {
        input.current = element
        if (directory && element) {
          element.setAttribute('webkitdirectory', '')
          element.setAttribute('directory', '')
        }
      }}
      onChange={(event) => {
        const files = event.currentTarget.files
        if (files?.length) onPick(files)
        event.currentTarget.value = ''
      }} />
  </>
}
