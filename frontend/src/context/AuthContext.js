import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=logged out, object=logged in

  useEffect(() => {
    const token = localStorage.getItem("sk_token");
    if (!token) {
      setUser(false);
      return;
    }
    api
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem("sk_token");
        setUser(false);
      });
  }, []);

  const login = (token, userObj) => {
    localStorage.setItem("sk_token", token);
    setUser(userObj);
  };

  const logout = () => {
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
