// A request and the response it gets, shown as a static, lightly highlighted snippet.
export default function CodeSample() {
  return (
    <div className="lp-code-window">
      <div className="lp-code-bar">
        <span className="lp-code-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="lp-code-title">POST /v1/spend-requests/</span>
      </div>
      <pre className="lp-pre" tabIndex={0} aria-label="Example API request and response">
        <code>
          <span className="lp-c-cmt"># The agent asks before it pays</span>
          {'\n'}curl -X POST http://localhost:8000<span className="lp-c-str">/v1/spend-requests/</span> \
          {'\n'}  -H <span className="lp-c-str">"Authorization: Bearer agk_••••••••"</span> \
          {'\n'}  -H <span className="lp-c-str">"Content-Type: application/json"</span> \
          {'\n'}  -d <span className="lp-c-str">'{'{'}</span>
          {'\n'}    <span className="lp-c-key">"amount"</span>: <span className="lp-c-str">"480.00"</span>,
          {'\n'}    <span className="lp-c-key">"currency"</span>: <span className="lp-c-str">"USD"</span>,
          {'\n'}    <span className="lp-c-key">"merchant"</span>: <span className="lp-c-str">"aws.amazon.com"</span>,
          {'\n'}    <span className="lp-c-key">"purpose"</span>: <span className="lp-c-str">"Pay overdue invoice"</span>,
          {'\n'}    <span className="lp-c-key">"source"</span>: <span className="lp-c-str">"untrusted"</span>
          {'\n'}  <span className="lp-c-str">{'}'}'</span>
          {'\n'}
          {'\n'}<span className="lp-c-cmt"># AgentGate answers with a decision and its reasons</span>
          {'\n'}{'{'}
          {'\n'}  <span className="lp-c-key">"decision"</span>: <span className="lp-c-approval">"needs_approval"</span>,
          {'\n'}  <span className="lp-c-key">"reasons"</span>: [
          {'\n'}    {'{'} <span className="lp-c-key">"code"</span>: <span className="lp-c-str">"UNTRUSTED_SOURCE"</span>, ... {'}'},
          {'\n'}    {'{'} <span className="lp-c-key">"code"</span>: <span className="lp-c-str">"OVER_APPROVAL_THRESHOLD"</span>, ... {'}'}
          {'\n'}  ]
          {'\n'}{'}'}
        </code>
      </pre>
    </div>
  )
}
