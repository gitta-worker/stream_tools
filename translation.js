"use strict";

const DEFAULT_API_ORIGIN = "http://127.0.0.1:5000";
const POLL_INTERVAL_MS = 500;

function getApiUrl() {
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
        return new URL("/api/translation/latest", window.location.origin).toString();
    }

    return `${DEFAULT_API_ORIGIN}/api/translation/latest`;
}

const API_URL = getApiUrl();

const japaneseElement = document.querySelector("#text-ja");
const englishElement = document.querySelector("#text-en");
let lastVersion = -1;

async function refreshTranslation() {
    try {
        const response = await fetch(API_URL, { cache: "no-store" });
        if (!response.ok) {
            return;
        }

        const data = await response.json();
        if (data.version === lastVersion) {
            return;
        }

        lastVersion = data.version;
        japaneseElement.textContent = data.text_ja ?? "";
        englishElement.textContent = data.text_en ?? "";
        japaneseElement.hidden = data.show_japanese === false;
        englishElement.hidden = data.show_english === false;
    } catch {
        // 起動直後など、翻訳サーバーが未準備の間は次回の取得を待つ。
    }
}

refreshTranslation();
setInterval(refreshTranslation, POLL_INTERVAL_MS);
