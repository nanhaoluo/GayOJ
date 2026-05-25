import assert from 'node:assert/strict';

const storage = new Map();

globalThis.localStorage = {
  getItem(key) {
    return storage.has(key) ? storage.get(key) : null;
  },
  setItem(key, value) {
    storage.set(key, String(value));
  },
  removeItem(key) {
    storage.delete(key);
  },
};

const {
  AUTH_TOKEN_KEY,
  apiRequest,
  clearStoredAuthToken,
  getStoredAuthToken,
  setStoredAuthToken,
} = await import('../apps/web/src/services/api.ts');

clearStoredAuthToken();
setStoredAuthToken('fresh-token');

assert.equal(localStorage.getItem(AUTH_TOKEN_KEY), 'fresh-token', 'fresh auth token should remain stored');
assert.equal(getStoredAuthToken(), 'fresh-token', 'stored auth token should be readable after login');

let requestHeaders = null;
globalThis.fetch = async (_url, init) => {
  requestHeaders = init.headers;
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => '{"ok":true}',
  };
};

await apiRequest('/auth/me');
assert.equal(requestHeaders.get('Authorization'), 'Bearer fresh-token', 'authenticated requests should send bearer token');

clearStoredAuthToken();
localStorage.setItem('ctoj_token', 'legacy-token');

assert.equal(getStoredAuthToken(), 'legacy-token', 'legacy token should migrate to current storage key');
assert.equal(localStorage.getItem(AUTH_TOKEN_KEY), 'legacy-token', 'legacy token should be copied to current key');
assert.equal(localStorage.getItem('ctoj_token'), null, 'legacy token key should be removed after migration');

clearStoredAuthToken();
assert.equal(localStorage.getItem(AUTH_TOKEN_KEY), null, 'current token should be cleared on logout');
assert.equal(localStorage.getItem('ctoj_token'), null, 'legacy token should be cleared on logout');

console.log('web auth token smoke passed');
