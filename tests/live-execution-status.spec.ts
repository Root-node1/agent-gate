import { expect, test, type Page } from '@playwright/test'

const requestId = 'cfd50dc7-6bd5-4fad-9a55-9defb534f81b'

const user = {
  id: 'user-1',
  email: 'reviewer@example.test',
  username: 'reviewer',
  first_name: '',
  last_name: '',
  date_joined: '2026-01-01T00:00:00Z',
  is_email_verified: true,
  memberships: [
    {
      organization_id: 'org-1',
      organization: 'Test workspace',
      role: 'admin',
    },
  ],
  profile: null,
}

function spendRequest(status: 'execution_blocked' | 'succeeded') {
  return {
    id: requestId,
    amount: '10.00',
    currency: 'USD',
    merchant: 'acme.com',
    purpose: 'Office supplies',
    source: 'untrusted',
    risk_score: 10,
    decision: 'allow',
    status,
    reasons: [],
    matched_rules: [],
    paypal_reference: status === 'succeeded' ? 'provider-ref-1' : null,
    created_at: '2026-11-10T12:00:00Z',
    approval: null,
  }
}

async function openRequest(page: Page, status: 'execution_blocked' | 'succeeded') {
  await page.route('**/api/auth/headless/browser/v1/auth/session', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ meta: { is_authenticated: true } }),
    }),
  )
  await page.route('**/api/auth/user/', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(user) }),
  )
  await page.route(`**/v1/spend-requests/${requestId}/`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(spendRequest(status)),
    }),
  )

  await page.goto(`/app/live/requests/${requestId}`)
  await page.getByLabel('Agent key').fill('agk_test-key')
  await expect(page.getByRole('heading', { name: 'Policy decision at submission' })).toBeVisible()
}

test('execution-blocked request is not presented as an allowed or completed payment', async ({
  page,
}) => {
  await openRequest(page, 'execution_blocked')

  await expect(page.getByText('Allowed at submission')).toBeVisible()
  const executionStatus = page.getByRole('status', { name: 'Execution status' })
  await expect(executionStatus).toContainText('Execution blocked')
  await expect(executionStatus).toContainText('No payment was sent')
  await expect(page.getByText('This payment can go ahead')).toHaveCount(0)
  await expect(page.getByText('Payment completed')).toHaveCount(0)
})

test('successful request shows provider completion separately from its policy decision', async ({
  page,
}) => {
  await openRequest(page, 'succeeded')

  await expect(page.getByText('Allowed at submission')).toBeVisible()
  await expect(page.getByLabel('Execution status')).toContainText('Payment completed')
})
