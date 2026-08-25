const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const json = await res.json();
  if (!res.ok || json.status === 'error') {
    const message = json.message || json.data?.message || 'Request failed';
    throw new Error(message);
  }
  return json;
}

export const api = {
  listAccounts: () => request('/accounts'),
  addAccount: (payload) => request('/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  updateAccount: (id, payload) => request(`/accounts/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  revealAccount: (id) => request(`/accounts/${id}/reveal`),
  deleteAccount: (id) => request(`/accounts/${id}`, { method: 'DELETE' }),
  connectAccount: (id) => request(`/accounts/${id}/connect`, { method: 'POST' }),
  disconnectAccount: (id) => request(`/accounts/${id}/disconnect`, { method: 'POST' }),

  listUpis: () => request('/upis'),
  addUpi: (payload) => request('/upis', { method: 'POST', body: JSON.stringify(payload) }),
  deleteUpi: (id) => request(`/upis/${id}`, { method: 'DELETE' }),

  getInstruments: () => request('/ipo/instruments'),
  getApplications: () => request('/ipo/applications'),
  apply: (payload) => request('/ipo/apply', { method: 'POST', body: JSON.stringify(payload) }),
  cancel: (accountId, appId) => request(`/accounts/${accountId}/ipo/applications/${appId}`, { method: 'DELETE' }),
};
