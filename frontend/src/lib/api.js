import axios from "axios";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
if (!/^https:\/\//i.test(BACKEND_URL)) {
  throw new Error(
    "REACT_APP_BACKEND_URL must be set to the production HTTPS backend before building the app.",
  );
}
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("sk_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function getToken() {
  return localStorage.getItem("sk_token");
}

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
