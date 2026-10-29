import { useContext } from "react";

import { AuthContext } from "./AuthProvider.jsx";

/** Read the current authentication context or report a missing provider. */
export function useAuth() {
  const auth = useContext(AuthContext);
  if (auth === null) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return auth;
}
