import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api";

const POLL_MS = 3000;

function fmtAmount(n) {
  return Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function isCredit(eventType) {
  return eventType === "DEPOSIT" || eventType === "TRANSFER_IN";
}

export default function App() {
  const [accounts, setAccounts] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [balance, setBalance] = useState(null);
  const [events, setEvents] = useState([]);
  const [feed, setFeed] = useState([]);
  const [summary, setSummary] = useState({ total_accounts: 0, total_transactions: 0, total_events: 0 });
  const [tab, setTab] = useState("ledger");
  const [error, setError] = useState(null);

  const [newAccount, setNewAccount] = useState({ owner_name: "", account_type: "WALLET", currency: "INR" });
  const [txnForm, setTxnForm] = useState({ amount: "", destination_account: "", description: "" });
  const [txnMode, setTxnMode] = useState("deposit");

  const selectedAccount = accounts.find((a) => a.id === selectedId);

  const refreshGlobal = useCallback(async () => {
    try {
      const [f, s, a] = await Promise.all([api.feed(40), api.summary(), api.listAccounts()]);
      setFeed(f);
      setSummary(s);
      setAccounts(a);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const refreshSelected = useCallback(async (id) => {
    if (!id) return;
    try {
      const [b, ev] = await Promise.all([api.getBalance(id), api.getEvents(id)]);
      setBalance(b.balance);
      setEvents(ev);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refreshGlobal();
    const t = setInterval(refreshGlobal, POLL_MS);
    return () => clearInterval(t);
  }, [refreshGlobal]);

  useEffect(() => {
    refreshSelected(selectedId);
    const t = setInterval(() => refreshSelected(selectedId), POLL_MS);
    return () => clearInterval(t);
  }, [selectedId, refreshSelected]);

  async function handleCreateAccount(e) {
    e.preventDefault();
    if (!newAccount.owner_name.trim()) return;
    try {
      const acc = await api.createAccount(newAccount);
      setNewAccount({ owner_name: "", account_type: "WALLET", currency: "INR" });
      await refreshGlobal();
      setSelectedId(acc.id);
    } catch (e2) {
      setError(e2.message);
    }
  }

  async function handleTxnSubmit(e) {
    e.preventDefault();
    if (!selectedId || !txnForm.amount) return;
    setError(null);
    try {
      if (txnMode === "deposit") {
        await api.deposit({ account_id: selectedId, amount: txnForm.amount, description: txnForm.description || null });
      } else if (txnMode === "withdraw") {
        await api.withdraw({ account_id: selectedId, amount: txnForm.amount, description: txnForm.description || null });
      } else {
        await api.transfer({
          source_account: selectedId,
          destination_account: txnForm.destination_account,
          amount: txnForm.amount,
          description: txnForm.description || null,
        });
      }
      setTxnForm({ amount: "", destination_account: "", description: "" });
      await Promise.all([refreshSelected(selectedId), refreshGlobal()]);
    } catch (e3) {
      setError(e3.message);
    }
  }

  // build running balance for display, oldest -> newest
  const orderedEvents = [...events].sort((a, b) => a.version - b.version);
  let running = 0;
  const rows = orderedEvents.map((ev) => {
    if (isCredit(ev.event_type)) running += Number(ev.amount);
    else if (ev.event_type !== "ACCOUNT_CREATED") running -= Number(ev.amount);
    return { ...ev, running };
  });
  rows.reverse(); // newest first for display

  return (
    <div className="app">
      <div className="masthead">
        <div>
          <h1>Ledger Core — Monitor</h1>
          <div className="sub">event-sourced double-entry ledger · live view</div>
        </div>
        <div className="stats">
          <div className="stat">
            <div className="value">{summary.total_accounts}</div>
            <div className="label">Accounts</div>
          </div>
          <div className="stat">
            <div className="value">{summary.total_transactions}</div>
            <div className="label">Transactions</div>
          </div>
          <div className="stat">
            <div className="value">{summary.total_events}</div>
            <div className="label">Events</div>
          </div>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="layout">
        {/* LEFT: accounts */}
        <div className="panel">
          <div className="panel-header">Chart of Accounts</div>
          <div>
            {accounts.length === 0 && <div className="empty">No accounts yet</div>}
            {accounts.map((a) => (
              <div
                key={a.id}
                className={`account-row ${a.id === selectedId ? "active" : ""}`}
                onClick={() => setSelectedId(a.id)}
              >
                <div>
                  <div className="name">{a.owner_name}</div>
                  <div className="type">{a.account_type} · {a.currency}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="panel-body">
            <form onSubmit={handleCreateAccount}>
              <div className="field">
                <label>Owner name</label>
                <input
                  value={newAccount.owner_name}
                  onChange={(e) => setNewAccount({ ...newAccount, owner_name: e.target.value })}
                  placeholder="e.g. Priya Sharma"
                />
              </div>
              <div className="field">
                <label>Account type</label>
                <select
                  value={newAccount.account_type}
                  onChange={(e) => setNewAccount({ ...newAccount, account_type: e.target.value })}
                >
                  <option value="WALLET">Wallet</option>
                  <option value="MERCHANT">Merchant</option>
                  <option value="REVENUE">Revenue</option>
                </select>
              </div>
              <button className="btn" type="submit">Open account</button>
            </form>
          </div>
        </div>

        {/* CENTER: ledger detail */}
        <div className="panel">
          {!selectedAccount && <div className="empty">Select or open an account to view its ledger</div>}
          {selectedAccount && (
            <>
              <div className="balance-block">
                <div>
                  <div className="owner">{selectedAccount.owner_name}</div>
                  <div className="sub" style={{ color: "var(--text-faint)", fontSize: 11 }}>
                    {selectedAccount.id}
                  </div>
                </div>
                <div className="amount">
                  {selectedAccount.currency} {balance !== null ? fmtAmount(balance) : "—"}
                </div>
              </div>

              <div className="tabs">
                <div className={`tab ${tab === "ledger" ? "active" : ""}`} onClick={() => setTab("ledger")}>
                  Ledger
                </div>
                <div className={`tab ${tab === "transact" ? "active" : ""}`} onClick={() => setTab("transact")}>
                  Transact
                </div>
              </div>

              {tab === "ledger" && (
                <div style={{ maxHeight: 480, overflowY: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        <th className="line-no">#</th>
                        <th>Event</th>
                        <th>Amount</th>
                        <th>Running balance</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.id}>
                          <td className="line-no">{r.version}</td>
                          <td>
                            <span className={`tag ${isCredit(r.event_type) ? "credit" : "debit"}`}>
                              {r.event_type}
                            </span>
                          </td>
                          <td className={isCredit(r.event_type) ? "credit" : "debit"}>
                            {r.event_type === "ACCOUNT_CREATED" ? "—" : `${isCredit(r.event_type) ? "+" : "-"}${fmtAmount(r.amount)}`}
                          </td>
                          <td>{fmtAmount(r.running)}</td>
                          <td style={{ color: "var(--text-faint)" }}>{fmtTime(r.created_at)}</td>
                        </tr>
                      ))}
                      {rows.length === 0 && (
                        <tr>
                          <td colSpan={5} className="empty">No events yet</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {tab === "transact" && (
                <div className="panel-body">
                  <div className="tabs" style={{ marginBottom: 12 }}>
                    {["deposit", "withdraw", "transfer"].map((m) => (
                      <div key={m} className={`tab ${txnMode === m ? "active" : ""}`} onClick={() => setTxnMode(m)}>
                        {m}
                      </div>
                    ))}
                  </div>
                  <form onSubmit={handleTxnSubmit}>
                    <div className="field">
                      <label>Amount</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={txnForm.amount}
                        onChange={(e) => setTxnForm({ ...txnForm, amount: e.target.value })}
                        required
                      />
                    </div>
                    {txnMode === "transfer" && (
                      <div className="field">
                        <label>Destination account</label>
                        <select
                          value={txnForm.destination_account}
                          onChange={(e) => setTxnForm({ ...txnForm, destination_account: e.target.value })}
                          required
                        >
                          <option value="">Select account</option>
                          {accounts.filter((a) => a.id !== selectedId).map((a) => (
                            <option key={a.id} value={a.id}>{a.owner_name}</option>
                          ))}
                        </select>
                      </div>
                    )}
                    <div className="field">
                      <label>Description (optional)</label>
                      <input
                        value={txnForm.description}
                        onChange={(e) => setTxnForm({ ...txnForm, description: e.target.value })}
                      />
                    </div>
                    <div className="btn-row">
                      <button className="btn" type="submit">Post {txnMode}</button>
                    </div>
                  </form>
                </div>
              )}
            </>
          )}
        </div>

        {/* RIGHT: live feed */}
        <div className="panel">
          <div className="panel-header">
            <span className="pulse-dot" />Live activity
          </div>
          <div style={{ maxHeight: 640, overflowY: "auto" }}>
            {feed.length === 0 && <div className="empty">Waiting for events…</div>}
            {feed.map((f) => (
              <div className="feed-item" key={f.id}>
                <div className="top">
                  <span className="owner">{f.owner_name}</span>
                  <span className="time">{fmtTime(f.created_at)}</span>
                </div>
                <div className={`amt ${isCredit(f.event_type) ? "credit" : "debit"}`}>
                  {f.event_type} {f.event_type !== "ACCOUNT_CREATED" ? fmtAmount(f.amount) : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}