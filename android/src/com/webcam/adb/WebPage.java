package com.webcam.adb;

/** Web viewer served at http://PHONE_IP:8080/ */
final class WebPage {
    private WebPage() { }

    static final String HTML = "<!doctype html>\n" +
            "<html lang=\"es\"><head><meta charset=\"utf-8\">\n" +
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n" +
            "<title>PocketLens</title>\n" +
            "<style>\n" +
            ":root{--bg:#0d0f12;--panel:#171a1f;--fg:#e8eaed;--mut:#8b929b;--acc:#2fbf71;--rec:#e5484d}\n" +
            "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}\n" +
            "header{display:flex;align-items:center;gap:10px;padding:12px 16px}\n" +
            "h1{font-size:17px;margin:0;font-weight:600}.dot{width:9px;height:9px;border-radius:50%;background:var(--mut)}\n" +
            ".live .dot{background:var(--rec)}#st{color:var(--mut);font-size:13px;margin-left:auto;text-align:right}\n" +
            "main{max-width:1100px;margin:0 auto;padding:0 16px 24px}\n" +
            ".view{position:relative;background:#000;border-radius:10px;overflow:hidden;aspect-ratio:16/9}\n" +
            ".view img{width:100%;height:100%;object-fit:contain;display:block;cursor:crosshair}\n" +
            ".bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px;background:var(--panel);padding:12px;border-radius:10px}\n" +
            "button{background:#252a31;color:var(--fg);border:0;border-radius:8px;padding:9px 14px;font:inherit;cursor:pointer}\n" +
            "button:hover{background:#2f353e}button.on{background:var(--acc);color:#04130a}\n" +
            "label{display:flex;align-items:center;gap:8px;color:var(--mut);flex:1;min-width:180px}input[type=range]{flex:1}\n" +
            "a{color:var(--acc)}p{color:var(--mut);font-size:13px}\n" +
            "</style></head><body>\n" +
            "<header id=\"hd\"><span class=\"dot\"></span><h1>PocketLens</h1><span id=\"st\">conectando…</span></header>\n" +
            "<main>\n" +
            "<div class=\"view\"><img id=\"v\" src=\"/video\" alt=\"cámara\"></div>\n" +
            "<div class=\"bar\">\n" +
            "<button id=\"sw\">Cambiar cámara</button><button id=\"tr\">Linterna</button>\n" +
            "<button id=\"sn\">Foto</button><button id=\"fs\">Pantalla completa</button>\n" +
            "<label>Zoom <input id=\"zm\" type=\"range\" min=\"1\" max=\"1\" step=\"0.1\" value=\"1\"></label>\n" +
            "<label>Exposición <input id=\"ex\" type=\"range\" min=\"0\" max=\"0\" step=\"1\" value=\"0\"></label>\n" +
            "</div>\n" +
            "<p>Toca la imagen para enfocar. Vista web en MJPEG (~15 fps). Para usar como webcam en Linux: <code>./webcam.sh --wifi IP</code>.</p>\n" +
            "</main>\n" +
            "<script>\n" +
            "const $=id=>document.getElementById(id);let busy=false;\n" +
            "function show(s){$('hd').className=s.clients+s.web>0?'live':'';\n" +
            " $('st').textContent=s.status+' · '+s.camera+' '+s.width+'x'+s.height+' · '+s.fps+' fps · '+(s.kbps/1000).toFixed(1)+' Mbps · PC '+s.clients+' · web '+s.web+' · audio '+s.audio;\n" +
            " $('tr').className=s.torch?'on':'';$('tr').disabled=!s.hasFlash;\n" +
            " const z=$('zm');z.min=s.minZoom;z.max=s.maxZoom;if(!busy)z.value=s.zoom;\n" +
            " const e=$('ex');e.min=s.expMin;e.max=s.expMax;if(!busy)e.value=s.exposure;}\n" +
            "async function api(p){try{const r=await fetch(p);show(await r.json());}catch(e){$('st').textContent='sin conexión';}}\n" +
            "$('sw').onclick=()=>{api('/api/switch');setTimeout(()=>{$('v').src='/video?'+Date.now()},1500)};\n" +
            "$('tr').onclick=()=>api('/api/torch');\n" +
            "$('sn').onclick=()=>{const a=document.createElement('a');a.href='/snapshot.jpg';a.download='foto.jpg';a.click()};\n" +
            "$('fs').onclick=()=>$('v').requestFullscreen&&$('v').requestFullscreen();\n" +
            "for(const [id,p] of [['zm','/api/zoom?v='],['ex','/api/exposure?v=']]){const el=$(id);\n" +
            " el.oninput=()=>{busy=true;api(p+el.value)};el.onchange=()=>{busy=false}}\n" +
            "$('v').onclick=ev=>{const r=ev.target.getBoundingClientRect();const iw=ev.target.naturalWidth||16,ih=ev.target.naturalHeight||9;\n" +
            " const s=Math.min(r.width/iw,r.height/ih),dw=iw*s,dh=ih*s;\n" +
            " const x=(ev.clientX-r.left-(r.width-dw)/2)/dw,y=(ev.clientY-r.top-(r.height-dh)/2)/dh;\n" +
            " if(x>=0&&x<=1&&y>=0&&y<=1)api('/api/focus?x='+x.toFixed(3)+'&y='+y.toFixed(3))};\n" +
            "$('v').onerror=()=>setTimeout(()=>{$('v').src='/video?'+Date.now()},2000);\n" +
            "api('/api/status');setInterval(()=>api('/api/status'),1000);\n" +
            "</script></body></html>\n";
}
