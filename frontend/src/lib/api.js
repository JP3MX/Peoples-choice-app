import axios from "axios";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
if (!/^https:\/\//i.test(BACKEND_URL)) {
  throw new Error(
    "REACT_APP_BACKEND_URL must be set to the production HTTPS backend before building the app.",
  );
}
export const API = `${BACKEND_URL}/api`;

// This backend authenticates with a session cookie (connect.sid), not a
// bearer token, so cross-origin requests must carry credentials.
export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("sk_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function getToken() {
  return localStorage.getItem("sk_token");
}

// Shared fetch() init for the raw fetch() calls (streaming chat, file
// downloads) that don't go through the axios instance above — carries the
// session cookie the same way `withCredentials` does for axios.
export const authFetchInit = { credentials: "include" };

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
