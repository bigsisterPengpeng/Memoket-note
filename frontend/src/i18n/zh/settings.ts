/** Chinese dictionary shard: settings (`components/SettingsPanel.tsx`). key = English source text, value = Chinese;
 *  `{name}` placeholders must match. Phrases shared across files (Save / Settings / Loading… / Interface language)
 *  live in `common.ts` and are not repeated here. */
export const SETTINGS: Record<string, string> = {
  // ---- feature labels in the usage block


  'Endless Continue': '无限续写',
  'Endless Continue · plan sections': '无限续写 · 定分段',
  '/ block': '/ 块生成',


  'Rewrite / polish': '重写 / 润色',


  'Digest': '定期回顾',

  'Memory relations': '记忆关系',
  'Skill generation': 'Skill 生成',
  'Extraction quality': '抽取质量',

  'Knowledge base extraction (estimated)': '知识库抽取（估算）',
  'Insert block': '插入块',


  '{group} · other': '{group} · 其他',
  // ---- usage
  '{calls} calls · {tok} tokens': '{calls} 次 · {tok} token',
  'Model usage': '模型用量',
  '24 hours': '24 小时',
  '7 days': '7 天',
  '30 days': '30 天',

  '{feature} · {calls} calls': '{feature} · {calls} 次',
  'Token counts come from provider responses, sorted by feature over the last 30 days; "Knowledge base extraction (estimated)" goes through KITE\'s own calls, which report no usage, so it is estimated from character counts.':
    'token 数取自供应商响应，按 30 天内的功能排；「知识库抽取（估算）」走 KITE 自己的调用，拿不到 usage，按字数估。',
  'Models: {models}': '模型：{models}',
  // ---- appearance
  'Follow system': '跟随系统',
  'Light': '浅色',
  'Dark': '深色',
  'Appearance': '外观',
  'The web version follows the system; only the desktop app can pick manually': '网页版只能跟随系统，桌面版才能手动选',
  'In a browser the theme follows the system; the desktop app can pin light / dark.': '浏览器里只能跟随系统；桌面版可以固定浅色 / 深色。',
  // ---- test button

  'Really connect to this address once; the result shows below': '真连一次这个地址，结果显示在下面',
  'Could not test: {why}': '测不了：{why}',

  'Connecting…': '正在连…',
  'Models available on this server — click one to fill in "Model":': '这台上有这些模型，点一个直接填进「模型名」：',
  'Available models': '可用模型',
  'This is the one currently entered': '就是现在填着的这个',
  'Use as model: {m}': '填进模型名：{m}',
  // ---- provenance line
  'MEMOKET NOTE · AGPL-3.0 · Source': 'MEMOKET NOTE · AGPL-3.0 · 源码',
  '· Reuses Trilium\'s design and theme (AGPL-3.0); dependency list in docs/third-party-notices.md': '· 复用了 Trilium 的设计与主题（AGPL-3.0），依赖清单见仓库 docs/third-party-notices.md',
  // ---- provider dropdown (labels of the backend presets that are not brand names are translated too)
  'Cloud services': '云端服务',
  'Local / self-hosted': '本机 / 自建',
  'Custom': '自定义',
  'Local / self-hosted (custom address)': '本地 / 自建（自定义地址）',
  'Custom OpenAI-compatible endpoint': '自定义 OpenAI 兼容端点',
  'Qwen / Alibaba Model Studio': 'Qwen / 阿里云百炼',
  'Zhipu GLM': '智谱 GLM',
  'Cleared the API key for {name}': '已清除 {name} 的 API key',
  'Could not clear: {why}': '清除失败：{why}',
  'Switched to {name}: {model} @ {url}': '已切换到{name}：{model} @ {url}',
  '(model not set)': '（模型名还没填）',
  'Saved, but the model is not fully set up — fill in the address and model name before AI features will work': '保存了，但模型还没配全——填上地址和模型名，AI 功能才用得了',
  'Save failed: {why}': '保存失败：{why}',


  'No model is set up yet, so none of the AI features work. Pick a provider below, fill it in, click "Test" to check it, then save.':
    '还没配模型，AI 功能全都用不了。下面选一档填上，填完点「测一下」看通不通，再保存。',
  'Writing model': '写作模型',
  'The model behind continue, revise and knowledge-base extraction — local models are free but slow; cloud providers need your own API key and are usually much faster. Each provider keeps its own key, so switching never loses one.':
    '续写、修订、知识库抽取这些功能背后调用的模型——本机模型免费但慢，云端那些档需要自己的 API key，通常快很多。每一档的 key 各存各的，切来切去不丢。',
  'Provider': '供应商',
  'Writing model provider': '写作模型供应商',
  'Model address (OpenAI-compatible)': '模型地址（OpenAI 兼容）',
  '{name} model address': '{name} 模型地址',

  'Ollama is http://127.0.0.1:11434/v1, LM Studio is http://127.0.0.1:1234/v1, llama.cpp / vLLM use their own /v1. Leave empty for the default.':
    'Ollama 是 http://127.0.0.1:11434/v1，LM Studio 是 http://127.0.0.1:1234/v1，llama.cpp / vLLM 填它们自己的 /v1。留空用默认。',
  'Base URL of any OpenAI-compatible endpoint (up to /v1). Requests are shaped like OpenAI\'s own.': '任意 OpenAI 兼容端点的 base URL（到 /v1 为止）。请求体按 OpenAI 官方的发。',
  'Leave empty for the official address; fill in a gateway / proxy address if you use one.': '留空用官方地址；走网关 / 代理时填网关的地址。',
  'Docs': '文档',
  'Model': '模型名',
  '{name} model': '{name} 模型名',
  'Default {model}': '默认 {model}',
  'e.g. {model}': '比如 {model}',
  'Type the model loaded on this server, or click "Test" and pick from the list': '填这台上加载的模型名，或点「测一下」从列表里选',
  'API key': 'API key',
  'API key (usually not needed locally)': 'API key（本地一般不用填）',
  '{name} API key': '{name} API key',
  'Set ({preview}); leave empty to keep it': '已设置 {preview}，留空则不改',
  'Most local servers do not check it; leave empty': '大多数本地服务不校验，留空即可',
  'Delete the key saved for this provider': '删掉这一档已存的 key',
  'Clear saved key': '清除已存的 key',
  'No API key set — even if saved, this provider will not be used and the app falls back to the local model.': '还没设置 API key，保存后选中这一档也用不了，会自动退回本地模型。',
  // ---- voice

  'Address of the whisper.cpp server used for transcription. Leave empty for the default; after saving, the "voice offline" status re-checks immediately.':
    '录音转写用的 whisper.cpp server 地址。留空用默认；改完保存，状态栏的「语音离线」会立刻重查。',

  // ---- vision
  'Vision (screen activity / image to table)': '看图（屏幕活动 / 图片转表格）',
  'Use the writing model above': '跟着上面的写作模型走',
  'Screenshots and images are sent to ': '截图和图片会发到',
  'the writing model\'s server': '写作模型那一台',
  '. To keep screenshots on this machine / your LAN, untick this and set a local vision model separately.': '。要让截图只留在本机 / 内网，就勾掉这一项，单独填一个本地的带视觉的模型。',
  '(not configured)': '（未配置）',
  'Screenshots go only here, ': '截图只发到这一处，',
  'independent of the writing provider above': '跟上面选的写作供应商无关',
  ' — switching writing to the cloud does not send screenshots there.': '——写作切到云端，截图也不会跟着出去。',
  'Vision model address': '看图模型地址',
  'Vision model (must support images)': '看图模型名（要带视觉）',
  'Vision model': '看图模型名',
  'Set; leave empty to keep it': '已设置，留空则不改',
  'Leave empty': '留空即可',
  'Vision API key': '看图 API key',
  'Test (sends an image)': '测一下（会发一张图）',
  // ---- notes <-> knowledge base
  'Notes ↔ knowledge base': '笔记 ↔ 知识库',
  'Sync notes to the knowledge base automatically after edits': '笔记改动后自动同步到知识库',
  'Only for notes already ingested: 2 minutes after you stop editing, or when you switch notes, the previously extracted facts are replaced (facts you added by hand stay). Each sync is one model call. When off, a yellow ⇡ in the tree marks notes edited but not synced.':
    '只对摄入过的笔记生效：停止编辑 2 分钟后、或切到别的笔记时，自动删掉上次抽的事实重新抽（你手工加的留着）。每次同步是一次模型调用。关着的话树上会用黄色 ⇡ 提醒你哪些改过没同步。',
}
