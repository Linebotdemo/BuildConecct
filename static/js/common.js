// /static/js/common.js

// JWTトークンを解析してペイロードを返す関数
function parseJwt(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      console.error("【DEBUG】トークンの形式が不正です:", token);
      return null;
    }
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonPayload);
    console.log("【DEBUG】parseJwt 成功:", payload);
    return payload;
  } catch (e) {
    console.error("【DEBUG】JWT解析エラー:", e);
    return null;
  }
}

// Ajaxでフラグメントを読み込む関数
function loadContent(pageUrl, el) {
  console.log("【DEBUG】loadContent 呼び出し:", pageUrl);
  document.querySelectorAll('#sidebar .nav-link').forEach(link => {
    link.classList.remove('active');
  });
  if (el) {
    el.classList.add('active');
  }
  fetch(`../pages/${pageUrl}`)
    .then(response => {
      if (!response.ok) {
        throw new Error("読み込み失敗: " + response.status);
      }
      return response.text();
    })
    .then(html => {
      console.log("【DEBUG】loadContent 成功:", pageUrl);
      document.getElementById("contentArea").innerHTML = html;
    })
    .catch(err => {
      console.error("【DEBUG】loadContent エラー:", err);
      document.getElementById("contentArea").innerHTML = "<p>コンテンツの読み込みに失敗しました。</p>";
    });
}
