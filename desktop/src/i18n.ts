/**
 * Language of the shell's own user-visible text (menus, dialogs, tray). The English text is the
 * key: `t('Open data folder')` returns it as-is in English mode and looks it up in `zh` below in
 * Chinese mode, falling back to English when missing.
 *
 * The language comes from the renderer (`memoketDesktop.rememberLang(lang)`), which main.ts
 * persists in identity.json as `lang`. This file is the only place in desktop/src allowed to
 * contain Chinese (see the ALLOW list in frontend/scripts/check-i18n.mts).
 */

export type Lang = 'en' | 'zh'

let lang: Lang = 'en'

export function getLang(): Lang { return lang }

/** Returns true when the language actually changed. */
export function setLang(next: unknown): boolean {
  const l: Lang = next === 'zh' ? 'zh' : 'en'
  if (l === lang) return false
  lang = l
  return true
}

export type Params = Record<string, string | number>

export function t(en: string, params?: Params): string {
  const s = lang === 'zh' ? (zh[en] ?? en) : en
  return params ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : s
}

const zh: Record<string, string> = {
  // ---- application menu ----
  'File': '文件',
  'New note': '新建笔记',
  "Today's journal": '今天的日记',
  'Import…': '导入…',
  'Export all notes…': '导出全部笔记…',
  'Recently deleted': '最近删除',
  'Screen activity': '屏幕活动',
  'Close window': '关闭窗口',
  'Tabs': '标签',
  'New tab': '新建标签',
  'Close tab': '关闭标签',
  'Reopen closed tab': '重新打开刚关的',
  'Next tab': '下一个标签',
  'Previous tab': '上一个标签',
  'List all tabs': '列出全部标签',
  'Close other tabs': '关闭其他标签',
  'View': '视图',
  'Actual size': '实际大小',
  'Zoom in': '放大',
  'Zoom out': '缩小',
  'Help': '帮助',
  'Keyboard shortcuts': '快捷键一览',
  'Open backups folder': '打开备份文件夹',
  'Open data folder': '打开数据文件夹',
  'Open logs folder': '打开日志文件夹',
  'Export backend log…': '导出后端日志…',
  'Export failed': '导出失败',
  'Report an issue': '报告问题',
  // ---- tray ----
  'Screen activity: not recording': '屏幕活动：没在记',
  'Screen activity: recording': '屏幕活动：记录中',
  'Screen activity: paused': '屏幕活动：已暂停',
  'Screen activity: cannot capture the screen (grant Screen Recording permission in System Settings)':
    '屏幕活动：截不到屏（去系统设置里给屏幕录制权限）',
  '{n} segments recorded today - open': '今天已记 {n} 段 — 打开看看',
  'Start recording': '开始记录',
  'Resume recording': '继续记录',
  'Pause for 1 hour': '暂停 1 小时',
  'Pause until I turn it on again': '暂停到我再打开',
  'Stop and turn off': '停止并关掉',
  // ---- dialogs ----
  'Backend keeps crashing': '后端反复崩溃',
  'It has already been restarted twice automatically and will not be retried.\n\nLast log lines:\n{log}\n\nFull log: {file}':
    '已经自动重启过两次，不再重试。\n\n最后几行日志：\n{log}\n\n完整日志：{file}',
  '(no output)': '（没有输出）',
  'The backend could not be restarted': '后端没能重新启动',
  '{error}\n\nLast log lines:\n{log}\n\nFull log: {file}': '{error}\n\n最后几行日志：\n{log}\n\n完整日志：{file}',
  'The frontend has not been built': '前端还没构建',
  '{dir} has no index.html.\n\n': '{dir} 下没有 index.html。\n\n',
  'This installer is incomplete, please reinstall.': '这个安装包不完整，请重新安装。',
  'In development mode, build the frontend once first:\n    cd frontend && npm run build':
    '开发模式下先构建一次前端：\n    cd frontend && npm run build',
  'The backend could not start': '后端没能启动',
  '{error}\n\nLast log lines:\n{log}': '{error}\n\n最后几行日志：\n{log}',
  'Startup failed': '启动失败',
  '{error}\n\nFull log: {file}': '{error}\n\n完整日志：{file}',
  'Cannot find the backend venv: {venv}\nDevelopment mode needs it. Create the virtual environment under backend/ and install the dependencies first.':
    '找不到后端的 venv：{venv}\n开发模式需要它。先在 backend/ 下建好虚拟环境并装依赖。',
  'The backend did not come up within {sec} seconds (last error: {err})': '后端在 {sec} 秒内没能起来（最后一次：{err}）',
  'Choose a folder': '选择文件夹',
  'Export slides': '导出幻灯片',
  'Slides': '幻灯片',
}
