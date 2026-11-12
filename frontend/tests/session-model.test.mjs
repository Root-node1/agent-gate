import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/session/sessionModel.ts', import.meta.url), 'utf8')
const javascript = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const sessionModel = await import(
  `data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`
)

test('anonymous bootstrap does not request or invent a profile', async () => {
  let profileRequested = false
  const session = await sessionModel.resolveSession(
    async () => ({ status: 'anonymous', body: { status: 401 } }),
    async () => {
      profileRequested = true
      throw new Error('must not fetch profile')
    },
  )

  assert.deepEqual(session, { status: 'unauthenticated' })
  assert.equal(profileRequested, false)
})

test('pending MFA remains distinct and does not fetch a dashboard profile', async () => {
  let profileRequested = false
  const flow = { id: 'mfa_authenticate', is_pending: true, types: ['totp'] }
  const session = await sessionModel.resolveSession(
    async () => ({ status: 'pending', flow, body: { status: 401 } }),
    async () => {
      profileRequested = true
      throw new Error('must not fetch profile')
    },
  )

  assert.deepEqual(session, { status: 'pending', flow })
  assert.equal(profileRequested, false)
})

test('pending email verification routes separately from pending MFA', async () => {
  const mfaFlow = sessionModel.pendingAuthenticationFlow({
    kind: 'mfa',
    types: ['totp', 'recovery_codes'],
  })
  const emailFlow = sessionModel.pendingAuthenticationFlow({ kind: 'verify-email' })
  assert.equal(
    sessionModel.pendingAuthenticationPath(mfaFlow),
    '/mfa',
  )
  assert.equal(
    sessionModel.pendingAuthenticationPath(emailFlow),
    '/verify-email',
  )
  assert.equal(sessionModel.pendingAuthenticationPath({ id: 'unknown_flow' }), null)
})

test('authenticated users without memberships go to onboarding', () => {
  assert.equal(
    sessionModel.authenticatedHomePath({ memberships: [] }),
    '/onboarding',
  )
  assert.equal(
    sessionModel.authenticatedHomePath({
      memberships: [{ organization_id: 'org-id', organization: 'Example', role: 'admin' }],
    }),
    '/app',
  )
})

test('authenticated bootstrap requires the backend profile to confirm the user', async () => {
  const user = { id: 'user-id', email: 'user@example.com' }
  const session = await sessionModel.resolveSession(
    async () => ({ status: 'authenticated', body: { status: 200 } }),
    async () => user,
  )

  assert.deepEqual(session, { status: 'authenticated', user })
  await assert.rejects(
    sessionModel.resolveSession(
      async () => ({ status: 'authenticated', body: { status: 200 } }),
      async () => {
        throw new Error('profile unavailable')
      },
    ),
    /profile unavailable/,
  )
})

test('an expired profile session resolves to anonymous instead of a session error', async () => {
  const session = await sessionModel.resolveSession(
    async () => ({ status: 'authenticated', body: { status: 200 } }),
    async () => {
      const error = new Error('Authentication failed.')
      error.name = 'SessionExpiredError'
      throw error
    },
  )

  assert.deepEqual(session, { status: 'unauthenticated' })
})
