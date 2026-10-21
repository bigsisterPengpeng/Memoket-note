import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { createServer } from 'node:http'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

const require = createRequire(import.meta.url)
const { downloadElectronArtifactZip } = require('app-builder-lib/out/util/electronGet.js')
const { downloadArtifact, ElectronDownloadCacheMode } = require('@electron/get')

test('the packaging downloader verifies checksums and reuses its isolated cache', async () => {
  const payload = Buffer.from('Synthetic download compatibility fixture.\n')
  const digest = createHash('sha256').update(payload).digest('hex')
  const cacheDir = await mkdtemp(join(tmpdir(), 'memoket-download-test-'))
  const version = '99.0.0'
  const filename = `electron-v${version}-darwin-arm64.zip`
  let requests = 0
  const server = createServer((_request, response) => {
    requests++
    response.writeHead(200, { 'Content-Length': payload.length })
    response.end(payload)
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const mirrorOptions = { mirror: `http://127.0.0.1:${server.address().port}/` }
  try {
    const options = {
      artifactName: 'electron', version, platformName: 'darwin', arch: 'arm64', cacheDir,
      electronDownload: { mirrorOptions, checksums: { [filename]: digest } },
    }
    const downloaded = await downloadElectronArtifactZip(options)
    assert.deepEqual(await readFile(downloaded), payload)
    const initialRequests = requests
    assert.ok(initialRequests > 0)
    const cached = await downloadElectronArtifactZip(options)
    assert.equal(cached, downloaded)
    assert.equal(requests, initialRequests)

    await assert.rejects(downloadArtifact({
      artifactName: 'electron', version, platform: 'darwin', arch: 'arm64',
      cacheRoot: cacheDir, cacheMode: ElectronDownloadCacheMode.Bypass, mirrorOptions,
      checksums: { [filename]: '0'.repeat(64) },
    }), /checksum|hash|match/i)
  } finally {
    await new Promise(resolve => server.close(resolve))
    await rm(cacheDir, { recursive: true, force: true })
  }
})
