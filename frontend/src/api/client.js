const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(message, status = 500, detail = null, code = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

export async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      credentials: 'include',
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorDetail = '';
      let errorCode = null;
      try {
        const errorData = await response.json();
        errorCode = errorData.code || null;
        errorDetail = errorData.detail || errorData.message || response.statusText;
      } catch {
        errorDetail = await response.text().catch(() => response.statusText);
      }
      throw new ApiError(errorDetail || `Request failed with status ${response.status}`, response.status, errorDetail, errorCode);
    }

    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error.message || 'Không thể kết nối đến máy chủ backend. Vui lòng thử lại.',
      0,
      error.message
    );
  }
}
