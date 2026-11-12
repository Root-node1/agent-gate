import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { loadTypeScriptModule } from './helpers/load-typescript.mjs'

const csrf = await loadTypeScriptModule('../../src/api/csrf.ts')
const client = await loadTypeScriptModule('../../src/api/client.ts', {
  './csrf': csrf.url,
})
const { module: paypal } = await loadTypeScriptModule('../../src/api/paypal.ts', {
  './client': client.url,
})

let originalFetch
let originalDocument
let originalWindow
let requests

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function useFetch(handler) {
  globalThis.fetch = async (input, init = {}) => {
    requests.push({ url: String(input), init })
    return handler(String(input), init)
  }
}

beforeEach(() => {
  originalFetch = globalThis.fetch
  originalDocument = globalThis.document
  originalWindow = globalThis.window
  globalThis.document = { cookie: 'csrftoken=csrf-token' }
  globalThis.window = new EventTarget()
  requests = []
})

afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalDocument === undefined) delete globalThis.document
  else globalThis.document = originalDocument
  if (originalWindow === undefined) delete globalThis.window
  else globalThis.window = originalWindow
})

test('fetchPayPalStatus calls GET /api/settings/paypal/status/ with session credentials', async () => {
  useFetch(async () =>
    jsonResponse({
      state: 'successfully_tested',
      mode: 'sandbox',
      live_payments_enabled: false,
      client_id_preview: 'AX1...99Z',
      webhook_configured: true,
      webhook_id_preview: 'WH-82...10',
      checkout_enabled: true,
      payouts_enabled: false,
      last_attempt_at: 1700000000,
      last_successful_at: 1700000000,
      last_attempt_error: null,
    }),
  )

  const status = await paypal.fetchPayPalStatus()
  assert.equal(requests[0].url, '/api/settings/paypal/status/')
  assert.equal(requests[0].init.method, 'GET')
  assert.equal(requests[0].init.credentials, 'include')
  assert.equal(status.state, 'successfully_tested')
  assert.equal(status.live_payments_enabled, false)
  assert.equal(status.client_id_preview, 'AX1...99Z')
})

test('triggerPayPalProbe calls POST /api/settings/paypal/probe/ with CSRF and empty body', async () => {
  useFetch(async () =>
    jsonResponse({
      state: 'successfully_tested',
      latency_ms: 245,
      tested_at: 1700000005,
      error: null,
    }),
  )

  const result = await paypal.triggerPayPalProbe()
  assert.equal(requests[0].url, '/api/settings/paypal/probe/')
  assert.equal(requests[0].init.method, 'POST')
  assert.equal(requests[0].init.credentials, 'include')
  assert.equal(new Headers(requests[0].init.headers).get('X-CSRFToken'), 'csrf-token')
  assert.equal(requests[0].init.body, '{}')
  assert.equal(result.state, 'successfully_tested')
  assert.equal(result.latency_ms, 245)
  assert.equal(result.tested_at, 1700000005)
  assert.equal(result.error, null)
})

test('triggerPayPalProbe surfaces sanitized error responses', async () => {
  useFetch(async () =>
    jsonResponse(
      {
        state: 'failed',
        latency_ms: 210,
        tested_at: 1700000005,
        error: 'invalid_credentials',
      },
      400,
    ),
  )

  await assert.rejects(
    async () => {
      await paypal.triggerPayPalProbe()
    },
    (err) => {
      assert.equal(err.status, 400)
      return true
    },
  )
})
