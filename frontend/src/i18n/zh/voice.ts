/** Chinese dictionary shard: Settings "Voice service" section (components/VoiceSettings.tsx). key = English source text, value = Chinese; `{name}` placeholders must match. */
export const VOICE: Record<string, string> = {

  'Which service transcribes recordings. After saving, the "voice offline" status in the status bar is rechecked right away.': '录音转写用哪家服务。改完保存，状态栏的「语音离线」会立刻重查。',
  'Whisper server (self-hosted)': 'Whisper 服务（自建）',
  'Free and local; needs a whisper.cpp server running on this machine or your network.': '免费、数据不出本地；需要本机或内网有一台 whisper.cpp server 开着。',
  'Hosted service; recordings are uploaded to AssemblyAI. Needs your own API key.': '云端服务，录音会上传到 AssemblyAI；需要你自己的 API key。',
  'Hosted service; recordings are uploaded to Speechmatics. Needs your own API key.': '云端服务，录音会上传到 Speechmatics；需要你自己的 API key。',
  'Server address': '服务地址',



  '{provider} API key': '{provider} API key',
  'Set {preview}; leave empty to keep it': '已设置 {preview}，留空则不改',
  'Paste your {provider} API key': '粘贴你的 {provider} API key',
  'An API key is saved.': '已存了 API key。',
  'No API key yet: transcription will not work until you add one and save.': '还没填 API key：填上并保存之前，转写用不了。',
  'Region': '区域',
  '{provider} region': '{provider} 区域',
  'EU': '欧盟',
  'US': '美国',
  'Paste an API key first': '先把 API key 粘进来',
  'Make one real request with these values; the result shows below': '用现在填的值真连一次，结果显示在下面',
  'Could not test: {error}': '测不了：{error}',

  'Connecting...': '正在连…',
}
