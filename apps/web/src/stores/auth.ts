import { reactive } from 'vue';
import { apiRequest, clearStoredAuthToken, getStoredAuthToken, setStoredAuthToken } from '@/services/api';
import type { PublicUser } from '@/services/types';

interface AuthState {
  user: PublicUser | null;
  loading: boolean;
  error: string;
}

export const authState = reactive<AuthState>({
  user: null,
  loading: false,
  error: '',
});

export async function login(username: string, password: string): Promise<void> {
  authState.loading = true;
  authState.error = '';
  try {
    const data = await apiRequest<{ access_token: string; user: PublicUser }>('/auth/login', {
      method: 'POST',
      auth: false,
      body: JSON.stringify({ username, password }),
    });
    setStoredAuthToken(data.access_token);
    authState.user = data.user;
  } catch (error) {
    authState.error = error instanceof Error ? error.message : '登录失败';
    throw error;
  } finally {
    authState.loading = false;
  }
}

export async function restoreSession(): Promise<void> {
  if (!getStoredAuthToken()) return;
  authState.loading = true;
  try {
    authState.user = await apiRequest<PublicUser>('/auth/me');
  } catch {
    clearStoredAuthToken();
    authState.user = null;
  } finally {
    authState.loading = false;
  }
}

export function setCurrentUser(user: PublicUser): void {
  authState.user = user;
}

export function logout(): void {
  clearStoredAuthToken();
  authState.user = null;
}
