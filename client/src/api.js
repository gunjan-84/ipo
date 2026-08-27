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
  authStatus: () => request('/auth/status'),
  authSetup: (payload) => request('/auth/setup', { method: 'POST', body: JSON.stringify(payload) }),
  authLogin: (payload) => request('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  authLogout: () => request('/auth/logout', { method: 'POST' }),

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

  listPans: () => request('/pans'),
  addPan: (payload) => request('/pans', { method: 'POST', body: JSON.stringify(payload) }),
  updatePan: (id, payload) => request(`/pans/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deletePan: (id) => request(`/pans/${id}`, { method: 'DELETE' }),

  getInstruments: () => request('/ipo/instruments'),
  getApplications: () => request('/ipo/applications'),
  apply: (payload) => request('/ipo/apply', { method: 'POST', body: JSON.stringify(payload) }),
  cancel: (accountId, appId) => request(`/accounts/${accountId}/ipo/applications/${appId}`, { method: 'DELETE' }),
  checkIpoStatus: ({ name, pan }) =>
    request(`/ipo/status?name=${encodeURIComponent(name)}&pan=${encodeURIComponent(pan)}`),
  listKfintechIpos: () => request('/ipo/kfintech-list'),
  listRegistryIpos: () => request('/ipo/registry'),
  checkAllotment: (clientId, registrar) =>
    request(`/ipo/allotment?client_id=${encodeURIComponent(clientId)}&registrar=${encodeURIComponent(registrar)}`),

  listGrowwAccounts: () => request('/groww/accounts'),
  addGrowwAccount: (payload) => request('/groww/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  updateGrowwAccount: (id, payload) => request(`/groww/accounts/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteGrowwAccount: (id) => request(`/groww/accounts/${id}`, { method: 'DELETE' }),
  connectGrowwAccount: (id) => request(`/groww/accounts/${id}/connect`, { method: 'POST' }),
  disconnectGrowwAccount: (id) => request(`/groww/accounts/${id}/disconnect`, { method: 'POST' }),
  getGrowwOrders: (id) => request(`/groww/accounts/${id}/orders`),
  growwLoginStart: (payload) => request('/groww/login/start', { method: 'POST', body: JSON.stringify(payload) }),
  growwLoginOtp: (payload) => request('/groww/login/otp', { method: 'POST', body: JSON.stringify(payload) }),
  applyGrowwIpo: (accountId, payload) =>
    request(`/groww/accounts/${accountId}/apply`, { method: 'POST', body: JSON.stringify(payload) }),
  cancelGrowwOrder: (accountId, orderId, searchId) =>
    request(
      `/groww/accounts/${accountId}/orders/${orderId}${searchId ? `?search_id=${encodeURIComponent(searchId)}` : ''}`,
      { method: 'DELETE' }
    ),

  getIpoPremiums: () => request('/ipo/premiums'),
  getIpoSubscriptionDetail: (slug) => request(`/ipo/subscription?slug=${encodeURIComponent(slug)}`),
};
