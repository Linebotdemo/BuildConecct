// static/js/local-storage.js

/**
 * ローカルストレージから値を取得する
 * @param {string} key - 取得するキー
 * @returns {string|null} - キーに対応する値、または存在しなければ null
 */
function getItem(key) {
    return localStorage.getItem(key);
}

/**
 * ローカルストレージに値を設定する
 * @param {string} key - 設定するキー
 * @param {string} value - 保存する値
 */
function setItem(key, value) {
    localStorage.setItem(key, value);
}

/**
 * ローカルストレージからキーを削除する
 * @param {string} key - 削除するキー
 */
function removeItem(key) {
    localStorage.removeItem(key);
}
