/** Give every test subprocess a disposable backend data directory, including gates that import app.main. */
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawn } from 'node:child_process'

const data = mkdtempSync(join(tmpdir(), 'memoket-frontend-tests-'))
const cleanup = () => rmSync(data, { recursive: true, force: true })
const command = process.argv[2]
if (!command) { cleanup(); throw new Error('Pass the test command from package.json') }
const child = spawn(command, {
  shell: true,
  stdio: 'inherit',
  env: { ...process.env, KITE_DATA_DIR: data, MEMOKET_SKIP_TOPIC_SETTLE: '1' },
})
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal))
child.on('error', (error) => { console.error(error); cleanup(); process.exitCode = 1 })
child.on('exit', (code, signal) => { cleanup(); process.exitCode = code ?? (signal ? 1 : 0) })
