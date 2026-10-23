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
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigInteger;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.RSAPublicKeySpec;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * 云盘令牌获取（原生登录版）
 *
 * 为什么不用 WebView：
 *   1) 云盘网页会用 mcloud:// 唤起自家 App，WebView 不认识该协议会停在 ERR_UNKNOWN_URL_SCHEME；
 *   2) 网页受同源策略限制，无法直接请求移动登录接口。
 * 原生实现两个都没有：HttpURLConnection 无 CORS 限制，且请求从用户手机发出（境内 IP），
 * 不会像中转服务器那样被风控拦截。
 */
public class MainActivity extends Activity {

    private static final String OBF = "SFBYWGMwYVNCUkdUUXFRYnEzTTBDa2RYc21YYTU0Z1dpUkpMX3BoZw==";
    private static final String OWNER = "WoShiYiGeManHuaJia";
    private static final String REPO = "yun139-ghpanel";

    private static final String UA_EDGE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            + "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0";
    private static final String SALT = "fetion.com.cn:";
    private static final String KEY_HEX_1 = "73634235495062495331515373756c734e7253306c673d3d"; // AES-192-CBC
    private static final String KEY_HEX_2 = "7150714477323633586746674c337538";                 // AES-128-ECB
    private static final String SMS_RSA_N =
            "9ec3874c5b705b9aeaffc80684f94ce59dd13dd78dfddf856081dbe4999c7c1382a335ee4fc73ed1a9efc6d923ce0862c703659e606e84df0e61f4bbf3d62e1ffa917906c70bb39d962b0b8a574d58f1d135461c3dad16de55d21b7fbcd425caec50d73ef5e8e6e6f0d86a956c8b1c70c6ab2357727d7762e084e2097be633dc1805d52cf725eda28ae1969c98508d8657c1cdb108d62bd3f94191d3de8c79432fa68d19afbfa4541492cf38c90e4bfa466740f00b5ca9159071b2d5b4fdfb55ba974e9865af5bb276fdedddab703f52f2240b861463f7622f5c22821271d46f4c89144e2128cd32f372503493a8f272e75ebe977b201c46dcd3aed0209c7635";
    private static final BigInteger SMS_RSA_E = BigInteger.valueOf(65537);

    private EditText etPhone, etCode;
    private TextView tvLog, tvTok;
    private Button btnSend, btnLogin, btnCopy, btnUp;
    private View panelResult;
    private Handler ui;
    private ExecutorService pool;
    private String lastToken = "", lastPhone = "";
    private int cdSec = 0;

    private static String tok() { return new StringBuilder(OBF).reverse().toString(); }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ui = new Handler(Looper.getMainLooper());
        pool = Executors.newSingleThreadExecutor();

        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.WHITE);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(20), dp(16), dp(24));
        sv.addView(root);
        setContentView(sv);

        TextView title = new TextView(this);
        title.setText("云盘令牌获取");
        title.setTextSize(20);
        title.setTextColor(Color.BLACK);
        root.addView(title);

        TextView sub = new TextView(this);
        sub.setText("原生通道登录：请求直接从你手机发出，不经中转服务器、不跳网页");
        sub.setTextSize(12);
        sub.setTextColor(0xFF7B8794);
        sub.setPadding(0, dp(6), 0, dp(14));
        root.addView(sub);

        TextView warn = new TextView(this);
        warn.setText("免责声明：本工具仅用于获取你本人名下账号的登录令牌。因使用产生的账号风险、数据变动或损失由使用者自行承担。\n\n"
                + "禁止牟利声明：本工具免费、非商业，严禁用于代签到收费、批量养号出售、转售令牌、商业刷量或任何违反中国移动服务协议的活动。\n\n"
                + "令牌属敏感凭据，请勿转发他人。");
        warn.setTextSize(12);
        warn.setTextColor(0xFF8A6100);
        warn.setPadding(dp(12), dp(12), dp(12), dp(12));
        warn.setBackground(pill(0xFFFFF8E6, 0xFFF2DFAE));
        root.addView(warn);

        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        if (!sp.getBoolean("agreed", false)) {
            new AlertDialog.Builder(this)
                    .setTitle("使用前须知")
                    .setMessage("本工具仅用于获取你本人名下账号的登录令牌，禁止用于任何牟利行为。\n\n"
                            + "因使用产生的账号风险与损失由使用者自行承担。")
                    .setCancelable(false)
                    .setPositiveButton("我已阅读并同意", (d, w) -> sp.edit().putBoolean("agreed", true).apply())
                    .setNegativeButton("退出", (d, w) -> finish())
                    .show();
        }

        addLabel(root, "手机号");
        etPhone = new EditText(this);
        etPhone.setHint("11 位手机号");
        etPhone.setInputType(android.text.InputType.TYPE_CLASS_PHONE);
        etPhone.setSingleLine(true);
        styleInput(etPhone);
        root.addView(etPhone);

        addLabel(root, "短信验证码");
        LinearLayout rowCode = new LinearLayout(this);
        rowCode.setOrientation(LinearLayout.HORIZONTAL);
        etCode = new EditText(this);
        etCode.setHint("收到的验证码");
        etCode.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        etCode.setSingleLine(true);
        styleInput(etCode);
        LinearLayout.LayoutParams cl = new LinearLayout.LayoutParams(0, dp(48), 1f);
        etCode.setLayoutParams(cl);
        rowCode.addView(etCode);

        btnSend = new Button(this);
        btnSend.setText("获取验证码");
        btnSend.setAllCaps(false);
        btnSend.setTextColor(Color.WHITE);
        btnSend.setBackground(pill(0xFF2F7DE1, 0));
        LinearLayout.LayoutParams sl = new LinearLayout.LayoutParams(0, dp(48), 0.9f);
        sl.setMargins(dp(10), 0, 0, 0);
        btnSend.setLayoutParams(sl);
        rowCode.addView(btnSend);
        root.addView(rowCode);

        btnLogin = new Button(this);
        btnLogin.setText("登录并抓取令牌");
        btnLogin.setAllCaps(false);
        btnLogin.setTextColor(Color.WHITE);
        btnLogin.setBackground(pill(0xFF2E7D32, 0));
        LinearLayout.LayoutParams ll = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        ll.setMargins(0, dp(16), 0, 0);
        btnLogin.setLayoutParams(ll);
        root.addView(btnLogin);

        // 结果区
        panelResult = new LinearLayout(this);
        ((LinearLayout) panelResult).setOrientation(LinearLayout.VERTICAL);
        panelResult.setVisibility(View.GONE);
        LinearLayout.LayoutParams pl = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        pl.setMargins(0, dp(16), 0, 0);
        panelResult.setLayoutParams(pl);

        tvTok = new TextView(this);
        tvTok.setTextSize(11);
        tvTok.setTextColor(0xFF37474F);
        tvTok.setPadding(dp(10), dp(10), dp(10), dp(10));
        tvTok.setBackground(pill(0xFFECEFF1, 0));
        panelResult.bringToFront();
        ((LinearLayout) panelResult).addView(tvTok);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        btnCopy = new Button(this);
        btnCopy.setText("复制令牌");
        btnCopy.setAllCaps(false);
        btnCopy.setTextColor(Color.WHITE);
        btnCopy.setBackground(pill(0xFF2F7DE1, 0));
        LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(0, dp(46), 1f);
        bl.setMargins(0, dp(8), 0, 0);
        btnCopy.setLayoutParams(bl);
        row2.addView(btnCopy);

        btnUp = new Button(this);
        btnUp.setText("存入后台托管");
        btnUp.setAllCaps(false);
        btnUp.setTextColor(Color.WHITE);
        btnUp.setBackground(pill(0xFF00695C, 0));
        LinearLayout.LayoutParams bl2 = new LinearLayout.LayoutParams(0, dp(46), 1f);
        bl2.setMargins(dp(10), dp(8), 0, 0);
        btnUp.setLayoutParams(bl2);
        row2.addView(btnUp);
        ((LinearLayout) panelResult).addView(row2);
        root.addView(panelResult);

        TextView logTitle = new TextView(this);
        logTitle.setText("执行日志");
        logTitle.setTextSize(13);
        logTitle.setTextColor(0xFF52606D);
        LinearLayout.LayoutParams tl = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tl.setMargins(0, dp(18), 0, dp(6));
        logTitle.setLayoutParams(tl);
        root.addView(logTitle);

        tvLog = new TextView(this);
        tvLog.setBackground(pill(0xFF101822, 0));
        tvLog.setTextColor(0xFF9FE08A);
        tvLog.setTextSize(11);
        tvLog.setPadding(dp(10), dp(10), dp(10), dp(10));
        tvLog.setText("就绪。\n");
        root.addView(tvLog);

        btnSend.setOnClickListener(v -> doSend());
        btnLogin.setOnClickListener(v -> doLogin());
        btnCopy.setOnClickListener(v -> {
            if (TextUtils.isEmpty(lastToken)) return;
            ClipboardManager cmg = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cmg != null) cmg.setPrimaryClip(ClipData.newPlainText("token", lastToken));
            toast("已复制到剪贴板");
        });
        btnUp.setOnClickListener(v -> upload(lastPhone, lastToken));
    }

    private void addLabel(LinearLayout root, String t) {
        TextView l = new TextView(this);
        l.setText(t);
        l.setTextSize(13);
        l.setTextColor(0xFF52606D);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.setMargins(0, dp(14), 0, dp(6));
        l.setLayoutParams(p);
        root.addView(l);
    }

    private void styleInput(EditText e) {
        e.setTextSize(16);
        e.setPadding(dp(12), dp(10), dp(12), dp(10));
        e.setBackground(pill(0xFFFFFFFF, 0xFFD5DBE0));
    }

    // ================= 交互 =================
    private void doSend() {
        String phone = etPhone.getText().toString().trim();
        if (!phone.matches("1\\d{10}")) { toast("手机号格式不对"); return; }
        hideKb();
        btnSend.setEnabled(false);
        log("① 建立邮箱会话…");
        pool.execute(() -> {
            try {
                Map<String, String> sess = getMailSession();
                log("   ✓ JSESSIONID 已获取");
                String j = sendSmsCode(phone, sess.get("cookie"));
                log("   ✓ 验证码已发送： " + j);
                ui.post(() -> { toast("验证码已发送"); startCd(); });
            } catch (Throwable e) {
                log("   ✗ " + e.getMessage(), true);
                ui.post(() -> { btnSend.setEnabled(true); toast("发送失败，请看日志"); });
            }
        });
    }

    private void doLogin() {
        final String phone = etPhone.getText().toString().trim();
        final String code = etCode.getText().toString().trim();
        if (!phone.matches("1\\d{10}")) { toast("手机号格式不对"); return; }
        if (!code.matches("\\d{4,8}")) { toast("验证码格式不对"); return; }
        hideKb();
        btnLogin.setEnabled(false);
        btnLogin.setText("登录中…");
        log("② 开始登录");
        pool.execute(() -> {
            try {
                Map<String, String> sess = getMailSession();
                String cookie = sess.get("cookie");
                log("   1) 会话建立 ✓");
                String[] sr = smsPasswordLogin(phone, code, cookie);
                String sid = sr[0], rmkey = sr[1];
                log("   2) 短信登录换 sid ✓");
                String artifact = exchangeArtifact(sid, rmkey);
                log("   3) 换 artifact ✓");
                String[] r = thirdPartyLogin(phone, artifact);
                String account = r[0], authorization = r[1];
                log("   4) 换云盘令牌 ✓  账号 " + account);
                lastToken = authorization;
                lastPhone = account;
                ui.post(() -> showResult(authorization, account));
            } catch (Throwable e) {
                log("   ✗ 失败：" + e.getMessage(), true);
                ui.post(() -> { btnLogin.setEnabled(true); btnLogin.setText("登录并抓取令牌"); toast("登录失败，请看日志"); });
            }
        });
    }

    private void showResult(String token, String phone) {
        btnLogin.setEnabled(true);
        btnLogin.setText("登录并抓取令牌");
        panelResult.setVisibility(View.VISIBLE);
        tvTok.setText(token);
        tvLog.append("✓ 令牌已获取，手机号 " + phone + "\n");
        toast("成功，可复制或存入后台");
    }

    private void startCd() {
        cdSec = 60;
        btnSend.setText(cdSec + "s");
        new Thread(() -> {
            while (cdSec > 0) {
                try { Thread.sleep(1000); } catch (InterruptedException e) { return; }
                cdSec--;
                final int s = cdSec;
                ui.post(() -> {
                    if (s <= 0) { btnSend.setEnabled(true); btnSend.setText("获取验证码"); }
                    else btnSend.setText(s + "s");
                });
            }
        }).start();
    }

    // ================= 网络 =================
    private static class Resp {
        int code; String body = ""; List<String> setCookies = new ArrayList<>();
        String location = "";
    }

    private Resp http(String url, String method, Map<String, String> headers, String body, boolean manualRedirect) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod(method == null ? "GET" : method);
        c.setInstanceFollowRedirects(!manualRedirect);
        c.setConnectTimeout(25000);
        c.setReadTimeout(25000);
        if (headers != null) for (Map.Entry<String, String> e : headers.entrySet())
            c.setRequestProperty(e.getKey(), e.getValue());
        if (body != null && body.length() > 0) {
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.flush();
            os.close();
        }
        Resp r = new Resp();
        r.code = c.getResponseCode();
        r.location = c.getHeaderField("Location");
        List<String> ck = c.getHeaderFields().get("Set-Cookie");
        if (ck != null) r.setCookies.addAll(ck);
        InputStream is = (r.code >= 400) ? c.getErrorStream() : c.getInputStream();
        if (is != null) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
            is.close();
            r.body = new String(bo.toByteArray(), "UTF-8");
        }
        c.disconnect();
        return r;
    }

    private Map<String, String> getMailSession() throws Exception {
        Map<String, String> h = new HashMap<>();
        h.put("User-Agent", UA_EDGE);
        h.put("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");
        h.put("Accept-Language", "zh-CN,zh;q=0.9");
        Exception last = null;
        for (int i = 0; i < 3; i++) {
            try {
                Resp r = http("https://mail.10086.cn/", "GET", h, null, true);
                if (r.code != 200 && r.code != 301 && r.code != 302)
                    throw new Exception("HTTP " + r.code);
                Map<String, String> jar = parseCookies(r.setCookies);
                String js = jar.get("JSESSIONID");
                if (TextUtils.isEmpty(js)) throw new Exception("首页未下发 JSESSIONID（可能被风控）");
                Map<String, String> out = new HashMap<>();
                StringBuilder sb = new StringBuilder();
                for (Map.Entry<String, String> e : jar.entrySet()) {
                    if (sb.length() > 0) sb.append("; ");
                    sb.append(e.getKey()).append("=").append(e.getValue());
                }
                out.put("jsession", js);
                out.put("cookie", sb.toString());
                return out;
            } catch (Exception e) {
                last = e;
                try { Thread.sleep(3000); } catch (InterruptedException ignored) {}
            }
        }
        throw new Exception("建立邮箱会话失败(已重试3次): " + (last != null ? last.getMessage() : "无响应"));
    }

    private Map<String, String> parseCookies(List<String> list) {
        Map<String, String> jar = new HashMap<>();
        if (list == null) return jar;
        for (String c : list) {
            String[] parts = c.split(";");
            for (String p : parts) {
                int eq = p.indexOf('=');
                if (eq <= 0) continue;
                String k = p.substring(0, eq).trim();
                String v = p.substring(eq + 1).trim();
                if (v.isEmpty()) continue;
                jar.put(k, v);
            }
        }
        return jar;
    }

    private String sendSmsCode(String phone, String cookie) throws Exception {
        String encPhone = rsaEncrypt(phone);
        String body = "<object><string name=\"loginName\">" + encPhone + "</string>"
                + "<string name=\"fv\">4</string><string name=\"clientId\">1003</string>"
                + "<string name=\"eMode\">1</string><string name=\"loginFailureUrl\"></string>"
                + "<string name=\"loginSuccessUrl\"></string><string name=\"verifyCode\"></string>"
                + "<string name=\"version\">1.0</string><string name=\"scene\">5</string></object>";
        Map<String, String> h = new HashMap<>();
        h.put("User-Agent", UA_EDGE);
        h.put("Content-Type", "text/plain; charset=UTF-8");
        h.put("Origin", "https://mail.10086.cn");
        h.put("Referer", "https://mail.10086.cn/");
        h.put("Accept", "*/*");
        h.put("Cookie", cookie);
        Resp r = http("https://mail.10086.cn/s?func=login:sendSmsCodeByScene&cguid=" + System.currentTimeMillis(),
                "POST", h, body, false);
        String t = r.body == null ? "" : r.body.trim();
        // 移动发码成功时 summary 为 "succeeded to process!"，code 并非 "0"，两者取其一
        boolean ok = t.contains("succeed") || t.contains("\"0\"") || t.contains("success") || t.contains("成功");
        if (!ok) throw new Exception("发码失败: " + t.substring(0, Math.min(120, t.length())));
        return "已发送";
    }

    private String[] smsPasswordLogin(String phone, String code, String cookie) throws Exception {
        String password = sha1Hex(SALT + code);
        String cguid = String.valueOf(System.currentTimeMillis());
        String referer = "https://mail.10086.cn/default.html?&s=1&v=0&u="
                + Base64.encodeToString(phone.getBytes("UTF-8"), Base64.NO_WRAP)
                + "&m=1&ec=S035&resource=indexLogin&clientid=1003&auto=on&cguid=" + cguid + "&mtime=45";
        StringBuilder form = new StringBuilder();
        form.append("UserName=").append(phone)
                .append("&passOld=&auto=on&Password=").append(password)
                .append("&webIndexPagePwdLogin=1&pwdType=1&clientId=1003&authType=2");
        Map<String, String> h = new HashMap<>();
        h.put("User-Agent", UA_EDGE);
        h.put("Content-Type", "application/x-www-form-urlencoded");
        h.put("Origin", "https://mail.10086.cn");
        h.put("Referer", referer);
        h.put("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");
        h.put("Cache-Control", "max-age=0");
        h.put("upgrade-insecure-requests", "1");
        h.put("Cookie", cookie);
        Resp r = http("https://mail.10086.cn/Login/Login.ashx", "POST", h, form.toString(), true);
        if (r.code != 200 && r.code != 301 && r.code != 302)
            throw new Exception("短信登录 HTTP " + r.code + ": " + safe(r.body, 120));
        Map<String, String> jar = parseCookies(r.setCookies);
        String loc = r.location == null ? "" : r.location;
        String ec = match(loc, "ec=([^&]+)");
        if (ec != null && !ec.equals("0") && !ec.equals("S_OK"))
            throw new Exception("登录被风控拦截(ec=" + ec + ")，可稍后重试");
        String sid = match(loc, "sid=([^&]+)");
        if (TextUtils.isEmpty(sid)) sid = jar.get("Os_SSo_Sid");
        String rmkey = jar.get("RMKEY");
        if (rmkey == null) rmkey = "";
        if (TextUtils.isEmpty(sid)) throw new Exception("未拿到 sid（验证码可能错误或已过期）");
        return new String[]{sid, rmkey};
    }

    private String exchangeArtifact(String sid, String rmkey) throws Exception {
        String url = "https://smsrebuild1.mail.10086.cn/setting/s?func=umc%3AgetArtifact&sid="
                + java.net.URLEncoder.encode(sid, "UTF-8") + "&cguid=" + System.currentTimeMillis();
        Map<String, String> h = new HashMap<>();
        h.put("Cookie", "RMKEY=" + rmkey);
        h.put("Content-Type", "text/xml; charset=utf-8");
        h.put("User-Agent", "okhttp/4.12.0");
        Resp r = http(url, "POST", h, "", true);
        String t = r.body == null ? "" : r.body.trim();
        // 移动此处返回单引号伪 JSON，做宽松解析
        String j = t.replace("'", "\"");
        String artifact = match(j, "\"artifact\"\\s*:\\s*\"([^\"]+)\"");
        if (TextUtils.isEmpty(artifact)) throw new Exception("换 artifact 失败: " + safe(t, 120));
        return artifact;
    }

    private String[] thirdPartyLogin(String phone, String dycpwd) throws Exception {
        String plainJson = "{\"clientkey_decrypt\":\"l3TryM&Q+X7@dzwk)qP\",\"clienttype\":\"886\","
                + "\"cpid\":\"507\",\"dycpwd\":\"" + dycpwd + "\","
                + "\"extInfo\":{\"ifOpenAccount\":\"0\"},\"loginMode\":\"0\",\"msisdn\":\"" + phone + "\","
                + "\"pintype\":\"13\",\"secinfo\":\"" + sha1Hex(SALT + dycpwd).toUpperCase() + "\","
                + "\"version\":\"20250901\"}";
        byte[] key1 = hexToBytes(KEY_HEX_1);
        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        byte[] enc = aesCbcEnc(plainJson.getBytes("UTF-8"), key1, iv);
        byte[] merged = new byte[iv.length + enc.length];
        System.arraycopy(iv, 0, merged, 0, iv.length);
        System.arraycopy(enc, 0, merged, iv.length, enc.length);
        String payload = Base64.encodeToString(merged, Base64.NO_WRAP);

        Map<String, String> h = new HashMap<>();
        h.put("hcy-cool-flag", "1");
        h.put("x-huawei-channelSrc", "10246600");
        h.put("x-MM-Source", "0");
        h.put("x-UserAgent", "android|23116PN5BC|android15|1.2.6|||1440x3200|10246600");
        h.put("x-DeviceInfo", "4|127.0.0.1|5|1.2.6|Xiaomi|23116PN5BC||02-00-00-00-00-00|android 15|1440x3200|android|||");
        h.put("Content-Type", "text/plain;charset=UTF-8");
        h.put("User-Agent", "okhttp/3.12.2");
        Resp r = http("https://user-njs.yun.139.com/user/thirdlogin", "POST", h, payload, true);
        String text = r.body == null ? "" : r.body.trim();

        String hexInner;
        if (text.startsWith("{")) {
            try { hexInner = new JSONObject(text).optString("data", ""); }
            catch (Exception e) { hexInner = match(text, "\"data\"\\s*:\\s*\"([^\"]+)\""); }
        } else {
            byte[] raw = Base64.decode(text, Base64.DEFAULT);
            if (raw.length < 32) throw new Exception("thirdlogin 响应解析失败: " + safe(text, 80));
            byte[] rIv = new byte[16], rCt = new byte[raw.length - 16];
            System.arraycopy(raw, 0, rIv, 0, 16);
            System.arraycopy(raw, 16, rCt, 0, rCt.length);
            byte[] plain = aesCbcDec(rCt, key1, rIv);
            String s1 = new String(plain, "UTF-8");
            try { hexInner = new JSONObject(s1).optString("data", ""); }
            catch (Exception e) { hexInner = match(s1, "\"data\"\\s*:\\s*\"([^\"]+)\""); }
        }
        if (TextUtils.isEmpty(hexInner)) throw new Exception("thirdlogin 无 data: " + safe(text, 80));
        byte[] inner = hexToBytes(hexInner);
        if (inner.length == 0 || inner.length % 16 != 0) throw new Exception("内层密文长度无效");
        byte[] key2 = hexToBytes(KEY_HEX_2);
        byte[] dec = aesEcbDec(inner, key2);
        String fj = new String(pkcs7Unpad(dec), "UTF-8");
        String authToken = match(fj, "\"authToken\"\\s*:\\s*\"([^\"]+)\"");
        String account = match(fj, "\"account\"\\s*:\\s*\"([^\"]+)\"");
        if (TextUtils.isEmpty(authToken) || TextUtils.isEmpty(account))
            throw new Exception("结果缺少 token: " + safe(fj, 100));
        String authorization = Base64.encodeToString(
                ("pc:" + account + ":" + authToken).getBytes("UTF-8"), Base64.NO_WRAP);
        return new String[]{account, authorization};
    }

    // ================= 加密 =================
    private static byte[] aesCbcEnc(byte[] data, byte[] key, byte[] iv) throws Exception {
        Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(iv));
        return c.doFinal(data);
    }

    private static byte[] aesCbcDec(byte[] data, byte[] key, byte[] iv) throws Exception {
        Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(iv));
        return c.doFinal(data);
    }

    private static byte[] aesEcbDec(byte[] data, byte[] key) throws Exception {
        Cipher c = Cipher.getInstance("AES/ECB/PKCS5Padding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"));
        return c.doFinal(data);
    }

    private static byte[] pkcs7Unpad(byte[] in) {
        if (in == null || in.length == 0) return new byte[0];
        int pad = in[in.length - 1] & 0xff;
        if (pad < 1 || pad > 16 || pad > in.length) return in;
        byte[] out = new byte[in.length - pad];
        System.arraycopy(in, 0, out, 0, out.length);
        return out;
    }

    private static byte[] hexToBytes(String hex) {
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++)
            out[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        return out;
    }

    private static String sha1Hex(String s) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-1");
        byte[] d = md.digest(s.getBytes("UTF-8"));
        StringBuilder sb = new StringBuilder();
        for (byte b : d) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    /** PKCS#1 v1.5 type 2 随机填充，与后端 rsaEncrypt 一致 */
    private static String rsaEncrypt(String text) throws Exception {
        byte[] msg = text.getBytes("UTF-8");
        int k = SMS_RSA_N.length() / 2;
        int psLen = k - msg.length - 3;
        if (psLen < 8) throw new Exception("RSA 明文过长");
        byte[] em = new byte[k];
        em[0] = 0;
        em[1] = 2;
        SecureRandom rnd = new SecureRandom();
        byte[] rndBuf = new byte[psLen];
        rnd.nextBytes(rndBuf);
        for (int i = 0; i < psLen; i++) {
            byte b = rndBuf[i];
            if (b == 0) b = 1; // 填充字节必须非零
            em[2 + i] = b;
        }
        em[2 + psLen] = 0;
        System.arraycopy(msg, 0, em, 3 + psLen, msg.length);
        BigInteger m = new BigInteger(1, em);
        BigInteger n = new BigInteger(SMS_RSA_N, 16);
        BigInteger c = m.modPow(SMS_RSA_E, n);
        byte[] cb = c.toByteArray();
        byte[] fixed = new byte[k];
        if (cb.length > k) System.arraycopy(cb, cb.length - k, fixed, 0, k);
        else System.arraycopy(cb, 0, fixed, k - cb.length, cb.length);
        return Base64.encodeToString(fixed, Base64.NO_WRAP);
    }

    // ================= 上传后台 =================
    private void upload(String phone, String token) {
        if (TextUtils.isEmpty(token) || TextUtils.isEmpty(phone)) { toast("没有令牌"); return; }
        toast("正在提交后台…");
        pool.execute(() -> {
            boolean ok = dispatch(phone, token);
            ui.post(() -> toast(ok ? "已提交，约 1 分钟内入库" : "提交失败，可改用复制令牌"));
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
            OutputStream os = conn.getOutputStream();
            os.write(body.toString().getBytes("UTF-8"));
            os.flush();
            os.close();
            return conn.getResponseCode() == 204;
        } catch (Throwable e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    // ================= 工具 =================
    private void log(String s) { log(s, false); }

    private void log(String s, boolean err) {
        ui.post(() -> {
            tvLog.append((err ? "✗ " : "  ") + s + "\n");
        });
    }

    private void toast(String m) {
        ui.post(() -> Toast.makeText(this, m, Toast.LENGTH_SHORT).show());
    }

    private void hideKb() {
        try {
            InputMethodManager im = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
            if (im != null && getCurrentFocus() != null)
                im.hideSoftInputFromWindow(getCurrentFocus().getWindowToken(), 0);
        } catch (Throwable ignored) {}
    }

    private static String match(String s, String regex) {
        if (s == null) return null;
        try {
            java.util.regex.Matcher m = java.util.regex.Pattern.compile(regex).matcher(s);
            return m.find() ? m.group(1) : null;
        } catch (Exception e) { return null; }
    }

    private static String safe(String s, int n) {
        if (s == null) return "";
        String t = s.replaceAll("\\s+", " ").trim();
        return t.length() > n ? t.substring(0, n) : t;
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density + 0.5f);
    }

    private GradientDrawable pill(int fill, int stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(8));
        if (stroke != 0) g.setStroke(1, stroke);
        return g;
    }

    @Override
    protected void onDestroy() {
        if (pool != null) pool.shutdownNow();
        super.onDestroy();
    }
}
