import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=logged out, object=logged in

  useEffect(() => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    // Handle Emergent Google OAuth callback: user returns to <origin>/#session_id=...
    const hash = window.location.hash || "";
    if (hash.includes("session_id=")) {
      const sid = new URLSearchParams(hash.replace(/^#/, "")).get("session_id");
      const cleanHash = () =>
        window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
      if (sid) {
        api
          .post("/auth/google/session", {}, { headers: { "X-Session-ID": sid } })
          .then((res) => {
            localStorage.setItem("sk_token", res.data.token);
            setUser(res.data.user);
            cleanHash();
          })
          .catch(() => {
            cleanHash();
            setUser(false);
          });
        return;
      }
    }

    // The backend authenticates with a JWT bearer token stored in
    // localStorage.sk_token (the api request interceptor attaches it). Ask the
    // backend whether that token is still valid; 401 => logged out.
    api
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem("sk_token");
        setUser(false);
      });
  }, []);

  const login = (userObj) => {
    setUser(userObj);
  };

  const logout = () => {
    api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("sk_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
