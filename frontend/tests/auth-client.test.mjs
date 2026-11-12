import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { loadTypeScriptModule } from './helpers/load-typescript.mjs'

const csrf = await loadTypeScriptModule('../../src/api/csrf.ts')
const client = await loadTypeScriptModule('../../src/api/client.ts', {
  './csrf': csrf.url,
})
const { module: auth } = await loadTypeScriptModule('../../src/api/auth.ts', {
  './client': client.url,
  './csrf': csrf.url,
})

let originalFetch
let originalDocument
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
  globalThis.document = { cookie: 'csrftoken=csrf-token' }
  requests = []
})

afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalDocument === undefined) delete globalThis.document
  else globalThis.document = originalDocument
})

test('CSRF bootstrap uses the public account endpoint and requires its cookie', async () => {
  useFetch(async (url, init) => {
    assert.equal(url, '/api/auth/csrf/')
    assert.equal(init.credentials, 'include')
    globalThis.document.cookie = 'csrftoken=csrf-token'
    return jsonResponse({ csrfToken: 'csrf-token' })
  })

  await auth.bootstrapCsrf()
  assert.equal(requests.length, 1)
  assert.equal(requests[0].init.method, undefined)
})

test('CSRF bootstrap reports failed requests and missing cookies', async () => {
  useFetch(async () => jsonResponse({}, 503))
  await assert.rejects(auth.bootstrapCsrf(), /HTTP 503/)

  globalThis.document.cookie = ''
  useFetch(async () => jsonResponse({ csrfToken: 'csrf-token' }))
  await assert.rejects(auth.bootstrapCsrf(), /did not set a CSRF cookie/)
})

test('unsafe requests bootstrap CSRF, send the header, and include credentials', async () => {
  globalThis.document.cookie = ''
  useFetch(async (url) => {
    if (url === '/api/auth/csrf/') {
      globalThis.document.cookie = 'csrftoken=csrf%2Ftoken'
      return jsonResponse({ csrfToken: 'csrf/token' })
    }
    return jsonResponse({ status: 200 })
  })

  await auth.headlessFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'user@example.com', password: 'secret' }),
  })

  assert.equal(requests.length, 2)
  assert.equal(requests[1].url, '/api/auth/headless/browser/v1/auth/login')
  assert.equal(requests[1].init.credentials, 'include')
  assert.equal(new Headers(requests[1].init.headers).get('X-CSRFToken'), 'csrf/token')
  assert.equal(new Headers(requests[1].init.headers).get('Content-Type'), 'application/json')
})

test('session classifies authenticated, anonymous, and pending states from allauth fields', async () => {
  const responses = [
    jsonResponse({ meta: { is_authenticated: true }, data: {} }, 200),
    jsonResponse({ meta: { is_authenticated: false }, data: { flows: [] } }, 401),
    jsonResponse(
      {
        meta: { is_authenticated: false },
        data: { flows: [{ id: 'mfa_authenticate', is_pending: true, types: ['totp'] }] },
      },
      401,
    ),
  ]
  useFetch(async (_url, init) => {
    assert.equal(init.credentials, 'include')
    return responses.shift()
  })

  assert.equal((await auth.getAuthenticationState()).status, 'authenticated')
  assert.equal((await auth.getAuthenticationState()).status, 'anonymous')
  const pending = await auth.getAuthenticationState()
  assert.equal(pending.status, 'pending')
  assert.equal(pending.flow.id, 'mfa_authenticate')
})

test('current user is fetched from the session-authenticated dashboard profile endpoint', async () => {
  useFetch(async (url, init) => {
    assert.equal(url, '/api/auth/user/')
    assert.equal(init.credentials, 'include')
    return jsonResponse({
      id: 'f4b07ff7-8337-4e98-8c48-6d3ac46b0a15',
      email: 'user@example.com',
      username: 'user',
      first_name: 'Test',
      last_name: 'User',
      date_joined: '2025-01-01T00:00:00Z',
      is_email_verified: true,
      memberships: [{
        organization_id: '719ed6ba-cf5f-45a0-8227-00fa3f47fdba',
        organization: 'Example',
        role: 'admin',
      }],
      profile: { full_name: 'Test User' },
    })
  })

  const user = await auth.getCurrentUser()
  assert.equal(user.email, 'user@example.com')
  assert.equal(
    user.memberships[0].organization_id,
    '719ed6ba-cf5f-45a0-8227-00fa3f47fdba',
  )
  assert.equal(user.memberships[0].role, 'admin')
})

test('workspace creation sends a session-authenticated CSRF-protected request', async () => {
  useFetch(async (url, init) => {
    assert.equal(url, '/api/auth/organizations/')
    assert.equal(init.method, 'POST')
    assert.equal(init.credentials, 'include')
    assert.equal(new Headers(init.headers).get('X-CSRFToken'), 'csrf-token')
    assert.deepEqual(JSON.parse(init.body), { name: 'Northstar Studio' })
    return jsonResponse({
      id: '719ed6ba-cf5f-45a0-8227-00fa3f47fdba',
      name: 'Northstar Studio',
      role: 'admin',
    }, 201)
  })

  assert.deepEqual(await auth.createOrganization('Northstar Studio'), {
    id: '719ed6ba-cf5f-45a0-8227-00fa3f47fdba',
    name: 'Northstar Studio',
    role: 'admin',
  })
})

test('workspace creation reports duplicate-name conflicts', async () => {
  useFetch(async () => jsonResponse({
    detail: 'A workspace with this name already exists.',
  }, 409))

  await assert.rejects(
    auth.createOrganization('Northstar Studio'),
    /A workspace with this name already exists/,
  )
})

test('login accepts server-confirmed success including the tested 409 response', async () => {
  const responses = [
    jsonResponse({ meta: { is_authenticated: true }, data: {} }, 200),
    jsonResponse({ meta: { is_authenticated: true }, data: {} }, 409),
  ]
  useFetch(async () => responses.shift())

  assert.deepEqual(await auth.signIn('user@example.com', 'password'), {
    kind: 'authenticated',
  })
  assert.deepEqual(await auth.signIn('user@example.com', 'password'), {
    kind: 'authenticated',
  })
})

test('login preserves pending MFA and email-verification flow distinctions', async () => {
  const responses = [
    jsonResponse(
      {
        meta: { is_authenticated: false },
        data: { flows: [{ id: 'mfa_authenticate', is_pending: true, types: ['totp'] }] },
      },
      401,
    ),
    jsonResponse(
      {
        meta: { is_authenticated: false },
        data: { flows: [{ id: 'verify_email', is_pending: true }] },
      },
      401,
    ),
  ]
  useFetch(async () => responses.shift())

  assert.deepEqual(await auth.signIn('user@example.com', 'password'), {
    kind: 'mfa',
    types: ['totp'],
  })
  assert.deepEqual(await auth.signIn('user@example.com', 'password'), {
    kind: 'verify-email',
  })
})

test('logout uses allauth DELETE and accepts its anonymous 401 response', async () => {
  globalThis.document.cookie = 'csrftoken=csrf-token'
  useFetch(async (_url, init) => {
    assert.equal(init.method, 'DELETE')
    assert.equal(init.credentials, 'include')
    assert.equal(new Headers(init.headers).get('X-CSRFToken'), 'csrf-token')
    return jsonResponse(
      { meta: { is_authenticated: false }, data: { flows: [] } },
      401,
    )
  })

  await auth.signOut()
  assert.equal(requests[0].url, '/api/auth/headless/browser/v1/auth/session')
})

test('signup sends only email and password and resolves the pending verify flow', async () => {
  useFetch(async (_url, init) => {
    assert.deepEqual(JSON.parse(init.body), {
      email: 'user@example.com',
      password: 'password',
    })
    return jsonResponse(
      {
        meta: { is_authenticated: false },
        data: { flows: [{ id: 'verify_email', is_pending: true }] },
      },
      401,
    )
  })

  assert.deepEqual(
    await auth.signUp({
      email: 'user@example.com',
      password: 'password',
      full_name: 'Unsupported name',
      organization: 'Unsupported organization',
      accept_terms: true,
    }),
    { kind: 'verify-email' },
  )
})

test('password reset accepts the tested anonymous success and rejects an errored 401', async () => {
  useFetch(async () =>
    jsonResponse(
      { meta: { is_authenticated: false }, data: { flows: [] } },
      401,
    ),
  )
  await auth.confirmPasswordReset('reset-key', 'new-password')

  useFetch(async () =>
    jsonResponse(
      {
        meta: { is_authenticated: false },
        errors: [{ code: 'invalid_password_reset', message: 'Reset key expired.' }],
      },
      401,
    ),
  )
  await assert.rejects(auth.confirmPasswordReset('bad-key', 'new-password'), (error) => {
    assert.equal(error.name, 'HeadlessError')
    assert.equal(error.status, 401)
    assert.equal(error.fieldErrors.key, 'Reset key expired.')
    return true
  })
})

test('password reset request and authenticated password change use their supported payloads', async () => {
  const responses = [
    jsonResponse({ status: 200, data: {} }),
    jsonResponse({ status: 200, data: {} }),
  ]
  useFetch(async (_url, init) => {
    assert.equal(init.credentials, 'include')
    return responses.shift()
  })

  await auth.requestPasswordReset('user@example.com')
  await auth.changePassword('current-password', 'new-password')

  assert.deepEqual(
    requests.map(({ url, init }) => [url, init.method, JSON.parse(init.body)]),
    [
      [
        '/api/auth/headless/browser/v1/auth/password/request',
        'POST',
        { email: 'user@example.com' },
      ],
      [
        '/api/auth/headless/browser/v1/account/password/change',
        'POST',
        { current_password: 'current-password', new_password: 'new-password' },
      ],
    ],
  )
})

test('API errors preserve server messages and field details', async () => {
  useFetch(async () =>
    jsonResponse(
      { errors: [{ param: 'password', message: 'Password is too common.' }] },
      400,
    ),
  )

  await assert.rejects(auth.signIn('user@example.com', 'password'), (error) => {
    assert.equal(error.name, 'HeadlessError')
    assert.equal(error.status, 400)
    assert.equal(error.message, 'Password is too common.')
    assert.equal(error.fieldErrors.password, 'Password is too common.')
    return true
  })
})

test('verification, reauthentication, TOTP, and recovery-code methods use allauth routes', async () => {
  const responses = [
    jsonResponse({ meta: { is_authenticated: false }, data: { flows: [] } }, 401),
    jsonResponse({ data: {} }),
    jsonResponse({ data: {} }),
    jsonResponse({ meta: { is_authenticated: true }, data: {} }),
    jsonResponse({ meta: { is_authenticated: true }, data: {} }),
    jsonResponse({ data: [{ type: 'totp' }] }),
    jsonResponse({ meta: { secret: 'setup-secret', totp_url: 'otpauth://totp/test' } }, 404),
    jsonResponse({ data: {} }),
    new Response(null, { status: 204 }),
    jsonResponse({ data: { unused_codes: ['12345678'] } }),
    jsonResponse({ data: { unused_codes: ['87654321'] } }),
    jsonResponse({ data: { unused_code_count: 1 } }),
  ]
  useFetch(async () => responses.shift())

  await auth.verifyEmail('email-code')
  await auth.resendVerificationCode()
  await auth.changeVerificationEmail('new@example.com')
  await auth.verifyMfa('123456')
  await auth.reauthenticate('password')
  assert.deepEqual(await auth.getAuthenticators(), [{ type: 'totp' }])
  assert.deepEqual(await auth.getTotpSetup(), {
    active: false,
    secret: 'setup-secret',
    totpUrl: 'otpauth://totp/test',
  })
  await auth.activateTotp('123456')
  await auth.removeTotp()
  assert.deepEqual(await auth.generateRecoveryCodes(), ['12345678'])
  assert.deepEqual(await auth.getRecoveryCodes(), ['87654321'])
  assert.deepEqual(await auth.getRecoveryCodes(), [])

  assert.deepEqual(
    requests.map(({ url, init }) => [url, init.method ?? 'GET']),
    [
      ['/api/auth/headless/browser/v1/auth/email/verify', 'POST'],
      ['/api/auth/headless/browser/v1/auth/email/verify/resend', 'POST'],
      ['/api/auth/headless/browser/v1/account/email', 'POST'],
      ['/api/auth/headless/browser/v1/auth/2fa/authenticate', 'POST'],
      ['/api/auth/headless/browser/v1/auth/reauthenticate', 'POST'],
      ['/api/auth/headless/browser/v1/account/authenticators', 'GET'],
      ['/api/auth/headless/browser/v1/account/authenticators/totp', 'GET'],
      ['/api/auth/headless/browser/v1/account/authenticators/totp', 'POST'],
      ['/api/auth/headless/browser/v1/account/authenticators/totp', 'DELETE'],
      ['/api/auth/headless/browser/v1/account/authenticators/recovery-codes', 'POST'],
      ['/api/auth/headless/browser/v1/account/authenticators/recovery-codes', 'GET'],
      ['/api/auth/headless/browser/v1/account/authenticators/recovery-codes', 'GET'],
    ],
  )
  assert.deepEqual(JSON.parse(requests[2].init.body), { email: 'new@example.com' })
})
