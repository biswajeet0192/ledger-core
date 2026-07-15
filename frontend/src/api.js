const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  listAccounts: () => request("/accounts"),
  createAccount: (payload) =>
    request("/accounts", { method: "POST", body: JSON.stringify(payload) }),
  getBalance: (accountId) => request(`/accounts/${accountId}/balance`),
  getEvents: (accountId) => request(`/accounts/${accountId}/events`),
  getAudit: (accountId) => request(`/accounts/${accountId}/audit`),
  deposit: (payload) =>
    request("/transactions/deposit", { method: "POST", body: JSON.stringify(payload) }),
  withdraw: (payload) =>
    request("/transactions/withdraw", { method: "POST", body: JSON.stringify(payload) }),
  transfer: (payload) =>
    request("/transactions/transfer", { method: "POST", body: JSON.stringify(payload) }),
  feed: (limit = 50) => request(`/monitor/feed?limit=${limit}`),
  summary: () => request("/monitor/summary"),
};

export const API_BASE_URL = BASE_URL;