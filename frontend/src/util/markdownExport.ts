export function downloadMarkdown(title: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${title.replace(/[/\\:*?"<>|\u0000-\u001f]/g, '-').trim() || 'Untitled'}.md`
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
