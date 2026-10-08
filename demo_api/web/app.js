"use strict";

const find = (id) => document.querySelector(`[data-testid="${id}"]`);
let token = null;
let users = [];
let editingId = null;

function message(id, text = "") {
  find(id).textContent = text;
  find(id).hidden = !text;
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "Invalid input";
    throw new Error(detail);
  }
  return data;
}

function renderUsers() {
  const query = find("search").value.toLowerCase();
  const visible = users.filter((user) => `${user.name} ${user.email}`.toLowerCase().includes(query));
  find("users-body").replaceChildren();
  for (const user of visible) {
    const row = document.createElement("tr");
    row.dataset.testid = "user-row";
    row.dataset.userId = user.id;
    for (const field of ["name", "email", "role"]) {
      const cell = document.createElement("td");
      cell.dataset.testid = `user-${field}`;
      // textContent не позволяет пользовательскому имени превратиться в исполняемый HTML.
      cell.textContent = user[field];
      row.append(cell);
    }
    const actions = document.createElement("td");
    for (const [label, id, handler] of [
      ["Edit", "edit-user", () => startEdit(user)],
      ["Delete", "delete-user", () => deleteUser(user.id)],
    ]) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.testid = id;
      button.textContent = label;
      button.addEventListener("click", handler);
      actions.append(button);
    }
    row.append(actions);
    find("users-body").append(row);
  }
  find("empty-state").hidden = visible.length !== 0;
}

async function refreshUsers() {
  find("users-body").dataset.loaded = "false";
  // Загружаем все страницы, иначе поиск и список не увидят записи после сотой.
  const loaded = [];
  let page;
  do {
    page = await request(`/users?limit=100&offset=${loaded.length}`);
    loaded.push(...page.items);
  } while (page.items.length > 0 && loaded.length < page.total);
  users = loaded;
  renderUsers();
  find("users-body").dataset.loaded = "true";
}

function startEdit(user) {
  editingId = user.id;
  find("edit-name").value = user.name;
  find("edit-form").hidden = false;
  message("user-error");
  message("user-notice");
}

async function deleteUser(id) {
  message("user-error");
  message("user-notice");
  try {
    await request(`/users/${id}`, { method: "DELETE" });
    if (editingId === id) {
      editingId = null;
      find("edit-form").hidden = true;
    }
    await refreshUsers();
    message("user-notice", "User deleted");
  } catch (error) {
    message("user-error", error.message);
  }
}

find("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  message("login-error");
  find("sign-in").disabled = true;
  try {
    const data = await request("/auth/token", {
      method: "POST",
      body: JSON.stringify({ username: find("username").value, password: find("password").value }),
    });
    token = data.access_token;
    await refreshUsers();
    find("login-panel").hidden = true;
    find("dashboard").hidden = false;
  } catch (error) {
    token = null;
    message("login-error", error.message);
  } finally {
    find("sign-in").disabled = false;
  }
});

find("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  message("user-error");
  message("user-notice");
  find("create-user").disabled = true;
  try {
    await request("/users", {
      method: "POST",
      body: JSON.stringify({ name: find("new-name").value, email: find("new-email").value, role: find("new-role").value }),
    });
    find("create-form").reset();
    await refreshUsers();
    message("user-notice", "User created");
  } catch (error) {
    message("user-error", error.message);
  } finally {
    find("create-user").disabled = false;
  }
});

find("edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  message("user-error");
  message("user-notice");
  find("save-user").disabled = true;
  try {
    await request(`/users/${editingId}`, { method: "PATCH", body: JSON.stringify({ name: find("edit-name").value }) });
    editingId = null;
    find("edit-form").hidden = true;
    await refreshUsers();
    message("user-notice", "User updated");
  } catch (error) {
    message("user-error", error.message);
  } finally {
    find("save-user").disabled = false;
  }
});

find("cancel-edit").addEventListener("click", () => {
  editingId = null;
  find("edit-form").hidden = true;
});
find("search").addEventListener("input", renderUsers);
find("refresh-users").addEventListener("click", () => {
  refreshUsers().catch((error) => message("user-error", error.message));
});
find("logout").addEventListener("click", () => {
  // Сессия живёт в памяти страницы; при выходе очищаем токен и показанные записи.
  token = null;
  users = [];
  editingId = null;
  find("search").value = "";
  find("create-form").reset();
  find("edit-form").hidden = true;
  find("login-form").reset();
  message("login-error");
  message("user-error");
  message("user-notice");
  renderUsers();
  find("dashboard").hidden = true;
  find("login-panel").hidden = false;
});
