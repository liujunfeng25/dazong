import { API_BASE } from "../config";

type Method = "GET" | "POST" | "PUT" | "DELETE";

export function getToken(): string {
  return uni.getStorageSync("dazong_token") || "";
}

export function setToken(token: string) {
  uni.setStorageSync("dazong_token", token);
}

export function clearToken() {
  uni.removeStorageSync("dazong_token");
}

export function request<T>(
  path: string,
  options: {
    method?: Method;
    data?: Record<string, unknown>;
    header?: Record<string, string>;
  } = {}
): Promise<T> {
  const { method = "GET", data, header } = options;
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method,
      data,
      header: {
        "Content-Type": "application/json",
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        ...(header || {}),
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T);
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      },
      fail: (e) => reject(e),
    });
  });
}
