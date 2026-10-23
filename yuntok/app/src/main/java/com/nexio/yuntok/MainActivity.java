package com.nexio.yuntok;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 云盘令牌获取
 *
 * 思路：用原生 WebView 打开云盘官方登录页，用户在本 App 内完成登录，
 * 登录成功后点右上角「保存令牌」，App 直接从 WebView 的 localStorage / Cookie 中读出
 * authorization。全程不跳转外部浏览器、不安装扩展、不经中转服务器登录。
 */
public class MainActivity extends Activity {

    private static final String HOME = "https://m.mcloud.139.com/";
    private static final String OBF = "SFBYWGMwYVNCUkdUUXFRYnEzTTBDa2RYc21YYTU0Z1dpUkpMX3BoZw==";
    private static final String OWNER = "WoShiYiGeManHuaJia";
    private static final String REPO = "yun139-ghpanel";

    private WebView web;
    private View panel;
    private TextView tvInfo;
    private TextView tvTok;
    private Button btnSave;
    private Handler ui;
    private ExecutorService pool;
    private String lastToken = "";
    private String lastPhone = "";

    private static String tok() { return new StringBuilder(OBF).reverse().toString(); }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ui = new Handler(Looper.getMainLooper());
        pool = Executors.newSingleThreadExecutor();

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setUserAgentString("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, String url) { return false; }
        });
        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        web.setWebChromeClient(new android.webkit.WebChromeClient());
        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        btnSave = new Button(this);
        btnSave.setText("保存令牌");
        btnSave.setTextColor(Color.WHITE);
        btnSave.setAllCaps(false);
        btnSave.setPadding(dp(14), dp(6), dp(14), dp(6));
        btnSave.setBackground(pill(0xFF2F7DE1));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT);
        lp.gravity = Gravity.TOP | Gravity.END;
        lp.setMargins(0, dp(56), dp(12), 0);
        root.addView(btnSave, lp);

        Button btnReload = new Button(this);
        btnReload.setText("刷新");
        btnReload.setTextColor(Color.WHITE);
        btnReload.setAllCaps(false);
        btnReload.setPadding(dp(12), dp(6), dp(12), dp(6));
        btnReload.setBackground(pill(0xCC455A64));
        FrameLayout.LayoutParams lp2 = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT);
        lp2.gravity = Gravity.TOP | Gravity.START;
        lp2.setMargins(dp(12), dp(56), 0, 0);
        root.addView(btnReload, lp2);
        btnReload.setOnClickListener(v -> web.loadUrl(HOME));

        panel = buildPanel();
        panel.setVisibility(View.GONE);
        FrameLayout.LayoutParams lp3 = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT);
        lp3.gravity = Gravity.BOTTOM;
        root.addView(panel, lp3);

        setContentView(root);

        web.loadUrl(HOME);

        btnSave.setOnClickListener(v -> grab());

        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        if (!sp.getBoolean("agreed", false)) showDisclaimer(sp);
    }

    private void showDisclaimer(SharedPreferences sp) {
        String msg =
                "免责声明\n\n"
                + "本工具仅用于获取你本人名下账号的登录令牌，以便自行托管签到。请确保你对所登录账号拥有合法使用权。\n\n"
                + "因使用本工具产生的任何账号风险、数据变动或损失，由使用者自行承担。\n\n"
                + "禁止牟利声明\n\n"
                + "本工具免费、非商业，严禁用于任何形式的牟利行为，包括但不限于：代签到收费、批量养号出售、"
                + "转售令牌、商业刷量或任何违反中国移动服务协议的活动。\n\n"
                + "令牌属于敏感凭据，请勿转发给他人。";
        new AlertDialog.Builder(this)
                .setTitle("使用前须知")
                .setMessage(msg)
                .setCancelable(false)
                .setPositiveButton("我已阅读并同意", (d, w) -> {
                    sp.edit().putBoolean("agreed", true).apply();
                })
                .setNegativeButton("退出", (d, w) -> finish())
                .show();
    }

    private View buildPanel() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackgroundColor(0xFFF4F6F8);
        box.setPadding(dp(14), dp(12), dp(14), dp(14));

        tvInfo = new TextView(this);
        tvInfo.setTextColor(0xFF37474F);
        tvInfo.setTextSize(13);
        box.addView(tvInfo);

        ScrollView sv = new ScrollView(this);
        LinearLayout.LayoutParams sl = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(90));
        sl.setMargins(0, dp(8), 0, dp(8));
        sv.setLayoutParams(sl);
        tvTok = new TextView(this);
        tvTok.setTextSize(11);
        tvTok.setTextColor(0xFF37474F);
        tvTok.setPadding(dp(8), dp(8), dp(8), dp(8));
        tvTok.setBackgroundColor(0xFFECEFF1);
        sv.addView(tvTok);
        box.addView(sv);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        Button bCopy = new Button(this);
        bCopy.setText("复制令牌");
        bCopy.setAllCaps(false);
        bCopy.setTextColor(Color.WHITE);
        bCopy.setBackground(pill(0xFF2F7DE1));
        LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(0, dp(46), 1f);
        bCopy.setLayoutParams(rl);
        row.addView(bCopy);

        Button bUp = new Button(this);
        bUp.setText("存入后台");
        bUp.setAllCaps(false);
        bUp.setTextColor(Color.WHITE);
        bUp.setBackground(pill(0xFF2E7D32));
        LinearLayout.LayoutParams rl2 = new LinearLayout.LayoutParams(0, dp(46), 1f);
        rl2.setMargins(dp(10), 0, 0, 0);
        bUp.setLayoutParams(rl2);
        row.addView(bUp);
        box.addView(row);

        Button bClose = new Button(this);
        bClose.setText("关闭");
        bClose.setAllCaps(false);
        bClose.setTextColor(0xFF607D8B);
        bClose.setBackground(pill(0xFFE0E0E0));
        LinearLayout.LayoutParams cl = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(40));
        cl.setMargins(0, dp(8), 0, 0);
        bClose.setLayoutParams(cl);
        box.addView(bClose);

        bCopy.setOnClickListener(v -> {
            if (TextUtils.isEmpty(lastToken)) return;
            ClipboardManager cmg = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cmg != null) cmg.setPrimaryClip(ClipData.newPlainText("token", lastToken));
            Toast.makeText(this, "已复制到剪贴板", Toast.LENGTH_SHORT).show();
        });
        bUp.setOnClickListener(v -> upload());
        bClose.setOnClickListener(v -> panel.setVisibility(View.GONE));
        return box;
    }

    // ---------- 抓取 ----------
    private void grab() {
        btnSave.setEnabled(false);
        btnSave.setText("读取中…");
        String js = "(function(){var it=[];try{for(var i=0;i<localStorage.length;i++){"
                + "var k=localStorage.key(i);var v=localStorage.getItem(k)||'';it.push({k:k,v:v});}}catch(e){}"
                + "var cd=document.cookie||'';"
                + "try{var cm=" + "document.cookie" + "; }catch(e2){}"
                + "return JSON.stringify({items:it,cookie:cd,url:location.href});})()";
        web.evaluateJavascript(js, value -> {
            String cookieStr = "";
            try {
                CookieManager cmg = CookieManager.getInstance();
                String c1 = cmg.getCookie(HOME);
                String c2 = cmg.getCookie("https://yun.139.com/");
                cookieStr = (c1 == null ? "" : c1) + ";" + (c2 == null ? "" : c2);
            } catch (Throwable ignore) {}
            parseAndShow(value, cookieStr);
            btnSave.setEnabled(true);
            btnSave.setText("保存令牌");
        });
    }

    private void parseAndShow(String rawJson, String sysCookie) {
        lastToken = "";
        lastPhone = "";
        List<String> cands = new ArrayList<>();
        try {
            String json = rawJson;
            if (json != null && json.startsWith("\"") && json.endsWith("\"")) {
                json = json.substring(1, json.length() - 1);
                json = json.replace("\\\"", "\"").replace("\\\\", "\\").replace("\\n", "\n");
            }
            JSONObject o = new JSONObject(json == null ? "{}" : json);
            JSONArray items = o.optJSONArray("items");
            if (items != null) {
                for (int i = 0; i < items.length(); i++) {
                    JSONObject it = items.optJSONObject(i);
                    if (it == null) continue;
                    String k = it.optString("k", "");
                    String v = it.optString("v", "");
                    if (v.length() > 16) cands.add(v);
                    if (v.length() > 16 && k.toLowerCase().contains("auth")) cands.add(0, v);
                }
            }
            String ck = o.optString("cookie", "");
            if (ck.length() > 0) cands.addAll(splitCookie(ck));
        } catch (Throwable ignore) {}

        cands.addAll(splitCookie(sysCookie == null ? "" : sysCookie));

        // 逐个候选：找出 base64 解码后形如 pc:手机号:token 的串
        for (String c : cands) {
            String[] ph = tryDecode(c);
            if (ph != null) { lastToken = c; lastPhone = ph[0]; break; }
        }
        // 兜底：key 含 authorization 的长串
        if (TextUtils.isEmpty(lastToken)) {
            for (String c : cands) {
                if (c.length() > 40 && !c.contains(" ")) { lastToken = c; break; }
            }
        }

        if (TextUtils.isEmpty(lastToken)) {
            panel.setVisibility(View.VISIBLE);
            tvInfo.setText("未读到令牌。请确认已在本页完成云盘登录（能看到自己的文件/云豆），"
                    + "登录后稍等两秒再点保存。");
            tvTok.setText("候选数量：" + cands.size());
            return;
        }
        panel.setVisibility(View.VISIBLE);
        tvInfo.setText("已读取到令牌" + (TextUtils.isEmpty(lastPhone) ? "" : "，手机号 " + lastPhone));
        tvTok.setText(lastToken);
    }

    private List<String> splitCookie(String ck) {
        List<String> out = new ArrayList<>();
        if (TextUtils.isEmpty(ck)) return out;
        String[] parts = ck.split(";");
        for (String p : parts) {
            String t = p.trim();
            int eq = t.indexOf('=');
            if (eq < 0) continue;
            String k = t.substring(0, eq).trim();
            String v = t.substring(eq + 1).trim();
            if (v.length() > 16 && k.toLowerCase().contains("auth")) out.add(0, v);
            else if (v.length() > 16) out.add(v);
        }
        return out;
    }

    /** 返回 [手机号] 或 null */
    private String[] tryDecode(String raw) {
        try {
            String s = raw.trim();
            if (s.toLowerCase().startsWith("basic ")) s = s.substring(6).trim();
            byte[] b = Base64.decode(s, Base64.DEFAULT);
            String d = new String(b, "UTF-8");
            if (!d.contains(":")) return null;
            String[] ps = d.split(":", 3);
            if (ps.length >= 2 && ps[1].matches("1\\d{10}")) return new String[]{ps[1]};
        } catch (Throwable ignore) {}
        return null;
    }

    // ---------- 上传后台 ----------
    private void upload() {
        if (TextUtils.isEmpty(lastToken)) { toast("没有令牌"); return; }
        String phone = lastPhone;
        if (TextUtils.isEmpty(phone)) { toast("未能识别手机号"); return; }
        final String p = phone, t = lastToken;
        toast("正在提交后台…");
        pool.execute(() -> {
            boolean ok = dispatch(p, t);
            ui.post(() -> toast(ok ? "已提交，后台约 1 分钟内入库" : "提交失败，可改用复制令牌"));
        });
    }

    private boolean dispatch(String phone, String token) {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(
                    "https://api.github.com/repos/" + OWNER + "/" + REPO + "/dispatches").openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Authorization", "token " + tok());
            conn.setRequestProperty("Accept", "application/vnd.github+json");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("User-Agent", "yuntok");
            conn.setDoOutput(true);
            conn.setConnectTimeout(20000);
            conn.setReadTimeout(20000);
            JSONObject cp = new JSONObject();
            cp.put("phone", phone);
            cp.put("authorization", token);
            JSONObject body = new JSONObject();
            body.put("event_type", "save_token");
            body.put("client_payload", cp);
            byte[] data = body.toString().getBytes("UTF-8");
            OutputStream os = conn.getOutputStream();
            os.write(data);
            os.flush();
            os.close();
            int code = conn.getResponseCode();
            return code == 204;
        } catch (Throwable e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    // ---------- 工具 ----------
    private void toast(String m) {
        ui.post(() -> Toast.makeText(this, m, Toast.LENGTH_SHORT).show());
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density + 0.5f);
    }

    private GradientDrawable pill(int color) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(8));
        return g;
    }

    @Override
    public void onBackPressed() {
        if (panel != null && panel.getVisibility() == View.VISIBLE) { panel.setVisibility(View.GONE); return; }
        if (web != null && web.canGoBack()) { web.goBack(); return; }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) { web.destroy(); }
        if (pool != null) pool.shutdownNow();
        super.onDestroy();
    }
}
