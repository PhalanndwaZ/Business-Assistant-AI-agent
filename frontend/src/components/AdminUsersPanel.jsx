import { useEffect, useState } from "react";

import {
  createAdminUser,
  listAdminUsers,
} from "../api/adminUsersApi.js";

const ROLES = ["sales", "hr", "manager", "admin"];
const USERS_PAGE = "#/admin/users";
const REGISTER_PAGE = "#/admin/users/new";

/** Resolve the current admin subpage from the browser hash. */
function getAdminPage() {
  return window.location.hash === REGISTER_PAGE ? "register" : "users";
}

/** Render registered users and account creation as separate admin pages. */
export function AdminUsersPanel() {
  const [page, setPage] = useState(getAdminPage);
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(function listenForAdminPageNavigation() {
    function updatePage() {
      setPage(getAdminPage());
      setError("");
    }

    window.addEventListener("hashchange", updatePage);
    return function removeAdminPageListener() {
      window.removeEventListener("hashchange", updatePage);
    };
  }, []);

  useEffect(function loadAccounts() {
    const controller = new AbortController();
    let active = true;

    async function fetchAccounts() {
      try {
        const accounts = await listAdminUsers({ signal: controller.signal });
        if (active) {
          setUsers(accounts);
        }
      } catch (requestError) {
        if (active && requestError?.kind !== "cancelled") {
          setError(requestError?.detail || requestError.message);
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    fetchAccounts();
    return function cancelAccountLoad() {
      active = false;
      controller.abort();
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsSaving(true);
    const form = event.currentTarget;
    const formData = new FormData(form);

    try {
      const account = await createAdminUser({
        username: formData.get("username"),
        name: formData.get("name"),
        role: formData.get("role"),
        password: formData.get("password"),
      });
      setUsers((currentUsers) =>
        [...currentUsers, account].sort((left, right) =>
          left.username.localeCompare(right.username),
        ),
      );
      setNotice(`Account ${account.username} was registered.`);
      form.reset();
      window.location.hash = USERS_PAGE;
    } catch (requestError) {
      setError(requestError?.detail || requestError.message);
    } finally {
      setIsSaving(false);
    }
  }

  const isRegisterPage = page === "register";

  return (
    <div className="chat-content admin-users">
      <header className="admin-users__intro">
        <p className="app-eyebrow">Administrator</p>
        <h1>{isRegisterPage ? "Register a user" : "Registered users"}</h1>
        <p>
          {isRegisterPage
            ? "Create an account and assign one of the four existing roles."
            : "View the accounts registered in the system."}
        </p>
      </header>

      <nav className="admin-users__nav" aria-label="User administration">
        <a
          aria-current={!isRegisterPage ? "page" : undefined}
          className={!isRegisterPage ? "admin-users__nav-link is-active" : "admin-users__nav-link"}
          href={USERS_PAGE}
        >
          Registered users
        </a>
        <a
          aria-current={isRegisterPage ? "page" : undefined}
          className={isRegisterPage ? "admin-users__nav-link is-active" : "admin-users__nav-link"}
          href={REGISTER_PAGE}
        >
          Register a user
        </a>
      </nav>

      {isRegisterPage ? (
        <section className="admin-users__section" aria-labelledby="register-user-title">
          <h2 id="register-user-title">New account details</h2>
          <form className="admin-users__form" onSubmit={handleSubmit}>
            <label>
              Name
              <input autoComplete="name" maxLength="120" name="name" required />
            </label>
            <label>
              Username
              <input
                autoComplete="username"
                maxLength="64"
                minLength="3"
                name="username"
                pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}"
                required
              />
            </label>
            <label>
              Role
              <select defaultValue="sales" name="role">
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Initial password
              <input
                autoComplete="new-password"
                maxLength="128"
                minLength="12"
                name="password"
                required
                type="password"
              />
              <span className="admin-users__hint">At least 12 characters.</span>
            </label>
            <button
              className="button button--primary"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Registering..." : "Register user"}
            </button>
          </form>
          {error ? (
            <p className="admin-users__error" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      ) : (
        <section className="admin-users__section" aria-labelledby="registered-users-title">
          <div className="admin-users__list-heading">
            <h2 id="registered-users-title">User accounts</h2>
            <a className="button button--primary" href={REGISTER_PAGE}>
              Register a user
            </a>
          </div>
          {notice ? (
            <p className="admin-users__notice" role="status">
              {notice}
            </p>
          ) : null}
          {error ? (
            <p className="admin-users__error" role="alert">
              {error}
            </p>
          ) : null}
          {isLoading ? <p role="status">Loading users...</p> : null}
          {!isLoading && users.length === 0 && !error ? (
            <p>No users are registered.</p>
          ) : null}
          {users.length > 0 ? (
            <div className="admin-users__table-wrap">
              <table className="admin-users__table">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Username</th>
                    <th scope="col">Role</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((account) => (
                    <tr key={account.user_id}>
                      <td>{account.name}</td>
                      <td>{account.username}</td>
                      <td>{account.role}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
