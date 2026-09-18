"use strict";

const form = document.querySelector("#setup-form");
const message = document.querySelector("#message");
const keyStatus = document.querySelector("#key-status");
const microphoneList = document.querySelector("#microphones");
const microphoneButton = document.querySelector("#load-microphones");
const customAppsContainer = document.querySelector("#custom-apps");
const customAppTemplate = document.querySelector("#custom-app-template");
const addCustomAppButton = document.querySelector("#add-custom-app");
let config = null;

function getValue(object, path) {
    return path.split(".").reduce((value, key) => value[key], object);
}

function setValue(object, path, value) {
    const keys = path.split(".");
    const lastKey = keys.pop();
    const parent = keys.reduce((value, key) => value[key], object);
    parent[lastKey] = value;
}

function populateForm() {
    for (const field of form.querySelectorAll("[data-path]")) {
        const value = getValue(config, field.dataset.path);
        if (field.type === "checkbox") {
            field.checked = value;
        } else if (field.dataset.path === "translation.deepl_auth_key") {
            field.value = "";
        } else {
            field.value = value ?? "";
        }
    }
    keyStatus.textContent = config.translation.deepl_auth_key_configured
        ? "認証キーは保存済みです。変更する場合だけ入力してください。"
        : "認証キーはまだ保存されていません。";
    renderCustomApps(config.custom_apps ?? []);
}

function addCustomAppRow(customApp = {}) {
    const row = customAppTemplate.content.firstElementChild.cloneNode(true);
    for (const field of row.querySelectorAll("[data-custom]")) {
        const value = customApp[field.dataset.custom];
        if (field.type === "checkbox") {
            field.checked = value ?? true;
        } else {
            field.value = value ?? "";
        }
    }
    row.querySelector(".remove-custom-app").addEventListener("click", () => row.remove());
    customAppsContainer.append(row);
}

function renderCustomApps(customApps) {
    customAppsContainer.replaceChildren();
    for (const customApp of customApps) {
        addCustomAppRow(customApp);
    }
}

function collectCustomApps() {
    return [...customAppsContainer.querySelectorAll(".custom-app-row")].map((row) => {
        const customApp = {};
        for (const field of row.querySelectorAll("[data-custom]")) {
            customApp[field.dataset.custom] = field.type === "checkbox"
                ? field.checked
                : field.value.trim();
        }
        return customApp;
    });
}

function collectForm() {
    for (const field of form.querySelectorAll("[data-path]")) {
        let value;
        if (field.type === "checkbox") {
            value = field.checked;
        } else if (field.type === "number") {
            value = field.value === "" ? null : Number(field.value);
        } else {
            value = field.value.trim();
        }
        setValue(config, field.dataset.path, value);
    }
    config.custom_apps = collectCustomApps();
    delete config.translation.deepl_auth_key_configured;
    return config;
}

async function loadConfig() {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) {
        throw new Error("設定を読み込めませんでした。");
    }
    config = await response.json();
    populateForm();
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.className = "";
    message.textContent = "保存しています…";
    try {
        const response = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectForm()),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error ?? "設定を保存できませんでした。");
        }
        config = result.config;
        populateForm();
        message.className = "success";
        message.textContent = "保存しました。設定を反映するにはランチャーを再起動してください。";
    } catch (error) {
        message.className = "error";
        message.textContent = error.message;
    }
});

microphoneButton.addEventListener("click", async () => {
    microphoneButton.disabled = true;
    message.textContent = "マイクを確認しています…";
    try {
        const response = await fetch("/api/microphones", { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error ?? "マイク一覧を取得できませんでした。");
        }
        microphoneList.replaceChildren(
            ...result.microphones.map(({ index, name }) => {
                const option = document.createElement("option");
                option.value = name;
                option.label = `${index}: ${name}`;
                return option;
            }),
        );
        message.textContent = `${result.microphones.length}件のマイクを取得しました。`;
    } catch (error) {
        message.className = "error";
        message.textContent = error.message;
    } finally {
        microphoneButton.disabled = false;
    }
});

addCustomAppButton.addEventListener("click", () => addCustomAppRow());

loadConfig().catch((error) => {
    message.className = "error";
    message.textContent = error.message;
});
