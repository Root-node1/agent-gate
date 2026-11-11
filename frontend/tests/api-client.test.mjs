import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { loadTypeScriptModule } from './helpers/load-typescript.mjs'

const csrf = await loadTypeScriptModule('../../src/api/csrf.ts')
const client = await loadTypeScriptModule('../../src/api/client.ts', {
  './csrf': csrf.url,
})
const { module: api } = client
const { module: agents } = await loadTypeScriptModule('../../src/api/agents.ts', {
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

test('session requests include cookies and unsafe methods include CSRF', async () => {
  useFetch(async (_url, init) => jsonResponse({ result: 'created' }, 201))

  assert.deepEqual(
    await api.apiRequest('/v1/resource/', {
      method: 'POST',
      body: { name: 'Example' },
    }),
    { result: 'created' },
  )
  assert.equal(requests[0].init.credentials, 'include')
  assert.equal(new Headers(requests[0].init.headers).get('X-CSRFToken'), 'csrf-token')
  assert.deepEqual(JSON.parse(requests[0].init.body), { name: 'Example' })
})

test('CSRF is bootstrapped from the backend when the cookie is absent', async () => {
  globalThis.document.cookie = ''
  useFetch(async (url, init) => {
    if (url === '/api/auth/csrf/') {
      assert.equal(init.credentials, 'include')
      globalThis.document.cookie = 'csrftoken=bootstrapped'
      return jsonResponse({ csrfToken: 'bootstrapped' })
    }
    return jsonResponse({ ok: true })
  })

  await api.apiRequest('/v1/resource/', { method: 'POST', body: {} })
  assert.equal(requests[0].url, '/api/auth/csrf/')
  assert.equal(
    new Headers(requests[1].init.headers).get('X-CSRFToken'),
    'bootstrapped',
  )
})

test('API errors preserve backend code, request id, details and field errors', async () => {
  useFetch(async () => jsonResponse({
    error: {
      code: 'validation_error',
      message: 'The request is invalid.',
      details: { name: ['This field is required.'] },
    },
    request_id: 'request-123',
  }, 400))

  await assert.rejects(
    api.apiRequest('/v1/resource/', { method: 'POST', body: {} }),
    (error) => {
      assert.ok(error instanceof api.ApiError)
      assert.equal(error.status, 400)
      assert.equal(error.code, 'validation_error')
      assert.equal(error.requestId, 'request-123')
      assert.deepEqual(error.fieldErrors, { name: ['This field is required.'] })
      return true
    },
  )
})

test('session 401 emits an expiry event and is distinct from authorization failure', async () => {
  let expiredEvents = 0
  globalThis.window.addEventListener(api.SESSION_EXPIRED_EVENT, () => expiredEvents++)
  useFetch(async () => jsonResponse({
    error: {
      code: 'authentication_failed',
      message: 'Authentication failed.',
      details: {},
    },
    request_id: 'expired-session',
  }, 401))

  await assert.rejects(
    api.apiRequest('/v1/resource/'),
    (error) => {
      assert.ok(error instanceof api.SessionExpiredError)
      assert.equal(error.requestId, 'expired-session')
      return true
    },
  )
  assert.equal(expiredEvents, 1)

  useFetch(async () => jsonResponse({
    error: { code: 'permission_denied', message: 'Forbidden.', details: {} },
  }, 403))
  await assert.rejects(
    api.apiRequest('/v1/resource/'),
    (error) => error instanceof api.ApiError && !(error instanceof api.SessionExpiredError),
  )
  assert.equal(expiredEvents, 1)
})

test('agent-key requests omit session credentials and do not trigger session expiry', async () => {
  let expiredEvents = 0
  globalThis.window.addEventListener(api.SESSION_EXPIRED_EVENT, () => expiredEvents++)
  useFetch(async (_url, init) => {
    assert.equal(init.credentials, 'omit')
    return jsonResponse({ detail: 'Agent suspended.' }, 403)
  })

  await assert.rejects(
    api.apiRequest('/v1/spend-requests/', { auth: 'agent', agentKey: 'agk_test' }),
    (error) => error instanceof api.ApiError && error.status === 403,
  )
  assert.equal(expiredEvents, 0)
  assert.equal(requests[0].init.headers.get('Authorization'), 'Bearer agk_test')
  assert.equal(requests[0].init.headers.get('X-CSRFToken'), null)
})

test('aborted requests remain cancellation errors and empty JSON responses fail explicitly', async () => {
  const controller = new AbortController()
  controller.abort()
  useFetch(async (_url, init) => {
    throw init.signal.reason
  })
  await assert.rejects(
    api.apiRequest('/v1/resource/', { signal: controller.signal }),
    (error) => error.name === 'AbortError',
  )

  useFetch(async () => new Response(null, { status: 204 }))
  await assert.rejects(
    api.apiRequest('/v1/resource/'),
    (error) => error instanceof api.ApiError && error.code === 'invalid_response',
  )
  assert.equal(await api.apiRequest('/v1/resource/', { allowEmptyResponse: true }), undefined)
})

test('organization-scoped list calls rely on the session, not a supplied organization ID', async () => {
  useFetch(async (url, init) => {
    assert.equal(url, '/v1/agents/?limit=25&offset=0')
    assert.equal(init.credentials, 'include')
    return jsonResponse({ count: 0, next: null, previous: null, results: [] })
  })

  const result = await agents.listAgents({ limit: 25, offset: 0 })
  assert.deepEqual(result.results, [])
  assert.equal(requests[0].url.includes('organization'), false)
})
