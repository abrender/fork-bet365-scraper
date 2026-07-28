function injectJs(href, callback){
    const script = document.createElement("script");
    script.setAttribute("type", "text/javascript");
    script.src = href;
    script.onload = callback;
    document.body.appendChild(script);
}

injectJs(chrome.runtime.getURL("js/hook.js"));



window.addEventListener("sendToAPI", async Ot => {
    const payload = Ot.detail || {};
    chrome.runtime.sendMessage({
        type: "SEND_HTTP",
        data: payload.data,
        lang: payload.lang
    });
})
