package com.nexio.yuntok;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
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

    // 版本标识：界面上直接显示，装完一眼可确认是不是新版
    private static final String APP_VER = "v7 · 邮箱版";
    private static final String BUILD_TS = "20261023-2115";

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
    private Button btnSend, btnLogin, btnCopy, btnFold;
    private LinearLayout histList;
    private boolean tokExpanded = false;
    private static final String HIST_KEY = "hist_v1";
    private static final String EKEY_KEY = "ekey_v1";
    private View panelResult;
    private Handler ui;
    private ExecutorService pool;
    private String lastToken = "", lastPhone = "";
    private int cdSec = 0;
    private List<String[]> histCache = new ArrayList<>();

    private static String tok() { return new StringBuilder(OBF).reverse().toString(); }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ui = new Handler(Looper.getMainLooper());
        pool = Executors.newSingleThreadExecutor();

        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(0xFFEFF3F9);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(14), dp(16), dp(14), dp(26));
        sv.addView(root);
        setContentView(sv);

        // ---------- 顶部渐变头 ----------
        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.VERTICAL);
        head.setBackground(grad(new int[]{0xFF5AA9F8, 0xFF154CB8}, 20));
        head.setPadding(dp(18), dp(18), dp(18), dp(18));
        root.addView(head);

        TextView hTitle = new TextView(this);
        hTitle.setText("\u2601  云盘令牌");
        hTitle.setTextSize(22);
        hTitle.setTypeface(null, Typeface.BOLD);
        hTitle.setTextColor(Color.WHITE);
        head.addView(hTitle);

        TextView hSub = new TextView(this);
        hSub.setText("原生登录 · 不含任何网页 · 请求从你手机直发");
        hSub.setTextSize(12);
        hSub.setTextColor(0xE6FFFFFF);
        hSub.setPadding(0, dp(5), 0, 0);
        head.addView(hSub);

        TextView hVer = new TextView(this);
        hVer.setText("版本 " + APP_VER + "  ·  构建 " + BUILD_TS);
        hVer.setTextSize(11);
        hVer.setTextColor(Color.WHITE);
        hVer.setPadding(dp(10), dp(6), dp(10), dp(6));
        hVer.setBackground(solid(0x33FFFFFF, 14));
        LinearLayout.LayoutParams vp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        vp.setMargins(0, dp(12), 0, 0);
        hVer.setLayoutParams(vp);
        head.addView(hVer);

        // ---------- 声明卡 ----------
        LinearLayout cNotice = card();
        TextView warn = new TextView(this);
        warn.setText("免责声明：本工具仅用于获取你本人名下账号的登录令牌，因使用产生的账号风险、数据变动或损失由使用者自行承担。\n\n"
                + "禁止牟利：本工具免费、非商业，严禁用于代签到收费、批量养号出售、转售令牌、商业刷量或任何违反中国移动服务协议的活动。\n\n"
                + "令牌属敏感凭据，请勿转发他人。");
        warn.setTextSize(12);
        warn.setTextColor(0xFF8A5A00);
        cNotice.addView(warn);
        root.addView(cNotice);

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

        // ---------- 登录卡 ----------
        LinearLayout cLogin = card();
        addLabel(cLogin, "手机号");
        etPhone = new EditText(this);
        etPhone.setHint("11 位手机号");
        etPhone.setInputType(android.text.InputType.TYPE_CLASS_PHONE);
        etPhone.setSingleLine(true);
        styleInput(etPhone);
        cLogin.addView(etPhone);

        addLabel(cLogin, "短信验证码");
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
        btnSend.setBackground(pressable(new int[]{0xFF4E97F7, 0xFF2C6FE0},
                new int[]{0xFF3A7FD8, 0xFF1B4EA8}, 24));
        LinearLayout.LayoutParams sl = new LinearLayout.LayoutParams(0, dp(48), 0.9f);
        sl.setMargins(dp(10), 0, 0, 0);
        btnSend.setLayoutParams(sl);
        rowCode.addView(btnSend);
        cLogin.addView(rowCode);

        btnLogin = new Button(this);
        btnLogin.setText("登录并抓取令牌");
        btnLogin.setAllCaps(false);
        btnLogin.setTextColor(Color.WHITE);
        btnLogin.setBackground(pressable(new int[]{0xFF3FA96B, 0xFF1E7A46},
                new int[]{0xFF2E8F58, 0xFF14603A}, 25));
        LinearLayout.LayoutParams ll = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        ll.setMargins(0, dp(16), 0, 0);
        btnLogin.setLayoutParams(ll);
        cLogin.addView(btnLogin);
        root.addView(cLogin);

        // ---------- 结果卡 ----------
        panelResult = card();
        ((LinearLayout) panelResult).setOrientation(LinearLayout.VERTICAL);
        panelResult.setVisibility(View.GONE);

        tvTok = new TextView(this);
        tvTok.setTextSize(11);
        tvTok.setTypeface(android.graphics.Typeface.MONOSPACE);
        tvTok.setTextColor(0xFF37474F);
        tvTok.setPadding(dp(10), dp(10), dp(10), dp(10));
        tvTok.setBackground(solid(0xFFECEFF1, 10));
        ((LinearLayout) panelResult).addView(tvTok);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        btnCopy = new Button(this);
        btnCopy.setText("复制令牌");
        btnCopy.setAllCaps(false);
        btnCopy.setTextColor(Color.WHITE);
        btnCopy.setBackground(pressable(new int[]{0xFF4E97F7, 0xFF2C6FE0},
                new int[]{0xFF3A7FD8, 0xFF1B4EA8}, 23));
        LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(0, dp(46), 1f);
        bl.setMargins(0, dp(10), 0, 0);
        btnCopy.setLayoutParams(bl);
        row2.addView(btnCopy);

        btnFold = new Button(this);
        btnFold.setText("展开完整令牌");
        btnFold.setAllCaps(false);
        btnFold.setTextColor(0xFF37474F);
        btnFold.setBackground(pressable(new int[]{0xFFE8EEF6, 0xFFD6E0EE},
                new int[]{0xFFCBD6E4, 0xFFB4C2D6}, 23));
        LinearLayout.LayoutParams bl2 = new LinearLayout.LayoutParams(0, dp(46), 1f);
        bl2.setMargins(dp(10), dp(10), 0, 0);
        btnFold.setLayoutParams(bl2);
        row2.addView(btnFold);
        ((LinearLayout) panelResult).addView(row2);
        root.addView(panelResult);

        // ---------- 历史卡 ----------
        LinearLayout cHist = card();
        LinearLayout hRow = new LinearLayout(this);
        hRow.setOrientation(LinearLayout.HORIZONTAL);
        hRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView hTitle2 = new TextView(this);
        hTitle2.setText("历史记录");
        hTitle2.setTextSize(13);
        hTitle2.setTextColor(0xFF52606D);
        LinearLayout.LayoutParams hp = new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        hTitle2.setLayoutParams(hp);
        hRow.addView(hTitle2);

        Button btnClear = new Button(this);
        btnClear.setText("清空");
        btnClear.setAllCaps(false);
        btnClear.setTextSize(12);
        btnClear.setTextColor(0xFFB0403A);
        btnClear.setBackground(pressable(new int[]{0xFFFDECEA, 0xFFF8DCD8},
                new int[]{0xFFF3D3CE, 0xFFE9BEB7}, 20));
        btnClear.setPadding(dp(14), dp(4), dp(14), dp(4));
        btnClear.setMinHeight(0);
        btnClear.setMinimumHeight(0);
        hRow.addView(btnClear);
        cHist.addView(hRow);

        TextView hTip = new TextView(this);
        hTip.setText("点击某条即复制该号令牌，长按可删除。令牌在本机加密保存。");
        hTip.setTextSize(11);
        hTip.setTextColor(0xFF8896A6);
        hTip.setPadding(0, dp(4), 0, dp(6));
        cHist.addView(hTip);

        histList = new LinearLayout(this);
        histList.setOrientation(LinearLayout.VERTICAL);
        cHist.addView(histList);
        root.addView(cHist);

        btnClear.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("清空历史")
                .setMessage("将删除本机保存的全部令牌记录，不可恢复。确定？")
                .setNegativeButton("取消", null)
                .setPositiveButton("清空", (d, w) -> {
                    getSharedPreferences("cfg", MODE_PRIVATE).edit().remove(HIST_KEY).apply();
                    histCache.clear();
                    renderHist();
                    toast("已清空");
                })
                .show());

        // ---------- 推送卡 ----------
        LinearLayout cPush = card();
        addLabel(cPush, "推送通知（钉钉 / 企业微信 / 飞书）");
        TextView pushTip = new TextView(this);
        pushTip.setText("网页端受浏览器跨域限制无法直接推送，推送在 App 内发送。");
        pushTip.setTextSize(11);
        pushTip.setTextColor(0xFF8B97A4);
        cPush.addView(pushTip);

        android.widget.Spinner spType = new android.widget.Spinner(this);
        spType.setAdapter(new android.widget.ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"钉钉群机器人", "企业微信群机器人", "飞书群机器人", "电子邮件(SMTP)"}));
        cPush.addView(spType);

        LinearLayout hookBox = new LinearLayout(this);
        hookBox.setOrientation(LinearLayout.VERTICAL);
        addLabel(hookBox, "Webhook 地址");
        EditText etHook = new EditText(this);
        etHook.setHint("粘贴机器人的完整 webhook 地址");
        etHook.setSingleLine(true);
        hookBox.addView(etHook);
        cPush.addView(hookBox);

        LinearLayout mailBox = new LinearLayout(this);
        mailBox.setOrientation(LinearLayout.VERTICAL);
        mailBox.setVisibility(android.view.View.GONE);
        TextView mailTip = new TextView(this);
        mailTip.setText("邮件走 SMTP，密码处请填邮箱「授权码」而不是登录密码。");
        mailTip.setTextSize(11);
        mailTip.setTextColor(0xFF8B97A4);
        mailBox.addView(mailTip);

        android.widget.Spinner spPreset = new android.widget.Spinner(this);
        spPreset.setAdapter(new android.widget.ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"常用邮箱预设…", "QQ邮箱", "163邮箱", "139邮箱", "Gmail", "Outlook", "自定义"}));
        mailBox.addView(spPreset);

        EditText etHost = new EditText(this);
        etHost.setHint("SMTP 服务器，如 smtp.qq.com");
        etHost.setSingleLine(true);
        mailBox.addView(etHost);

        EditText etPort = new EditText(this);
        etPort.setHint("端口：465(SSL) 或 587(STARTTLS)");
        etPort.setSingleLine(true);
        mailBox.addView(etPort);

        android.widget.CheckBox chkSsl = new android.widget.CheckBox(this);
        chkSsl.setText("直连 SSL（465 勾上；587 不勾）");
        chkSsl.setTextSize(12);
        mailBox.addView(chkSsl);

        EditText etUser = new EditText(this);
        etUser.setHint("邮箱账号（完整地址）");
        etUser.setSingleLine(true);
        mailBox.addView(etUser);

        EditText etPass = new EditText(this);
        etPass.setHint("授权码 / 密码");
        etPass.setSingleLine(true);
        etPass.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        mailBox.addView(etPass);

        EditText etTo = new EditText(this);
        etTo.setHint("收件邮箱（留空=发给自己）");
        etTo.setSingleLine(true);
        mailBox.addView(etTo);
        cPush.addView(mailBox);

        spType.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            public void onItemSelected(android.widget.AdapterView<?> p, android.view.View v, int pos, long id) {
                boolean mail = (pos == 3);
                hookBox.setVisibility(mail ? android.view.View.GONE : android.view.View.VISIBLE);
                mailBox.setVisibility(mail ? android.view.View.VISIBLE : android.view.View.GONE);
            }
            public void onNothingSelected(android.widget.AdapterView<?> p) { }
        });

        spPreset.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            public void onItemSelected(android.widget.AdapterView<?> p, android.view.View v, int pos, long id) {
                String[][] P = {{"", ""}, {"smtp.qq.com", "465"}, {"smtp.163.com", "465"},
                        {"smtp.139.com", "465"}, {"smtp.gmail.com", "587"}, {"smtp.office365.com", "587"}};
                if (pos >= 1 && pos <= 5) {
                    etHost.setText(P[pos][0]);
                    etPort.setText(P[pos][1]);
                    chkSsl.setChecked("465".equals(P[pos][1]));
                }
            }
            public void onNothingSelected(android.widget.AdapterView<?> p) { }
        });

        addLabel(cPush, "消息模板");
        android.widget.Spinner spTpl = new android.widget.Spinner(this);
        spTpl.setAdapter(new android.widget.ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"简洁版", "详细版", "仅异常", "极简单行", "自定义"}));
        cPush.addView(spTpl);

        EditText etTpl = new EditText(this);
        etTpl.setHint("自定义模板，可用 {time} {rows} {sum} {ok}");
        etTpl.setMinLines(3);
        etTpl.setVisibility(android.view.View.GONE);
        cPush.addView(etTpl);
        spTpl.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            public void onItemSelected(android.widget.AdapterView<?> p, android.view.View v, int pos, long id) {
                etTpl.setVisibility(pos == 4 ? android.view.View.VISIBLE : android.view.View.GONE);
                if (pos != 4) etTpl.setText(TPL[pos]);
            }
            public void onNothingSelected(android.widget.AdapterView<?> p) { }
        });

        LinearLayout rowP = new LinearLayout(this);
        rowP.setOrientation(LinearLayout.HORIZONTAL);
        Button btnImport = new Button(this);
        btnImport.setText("粘贴导入");
        btnImport.setLayoutParams(new LinearLayout.LayoutParams(0, dp(44), 1f));
        btnImport.setOnClickListener(v -> importPushCfg(etHook, etTpl, spType, spTpl));
        rowP.addView(btnImport);
        Button btnSaveP = new Button(this);
        btnSaveP.setText("保存");
        btnSaveP.setLayoutParams(new LinearLayout.LayoutParams(0, dp(44), 1f));
        btnSaveP.setOnClickListener(v -> {
            saveNotify(spType.getSelectedItemPosition(), etHook.getText().toString().trim(),
                    spTpl.getSelectedItemPosition(), etTpl.getText().toString());
            saveMail(etHost.getText().toString().trim(), portOf(etPort.getText().toString()),
                    chkSsl.isChecked(), etUser.getText().toString().trim(),
                    etPass.getText().toString().trim(), etTo.getText().toString().trim());
            toast("推送配置已保存");
        });
        rowP.addView(btnSaveP);
        Button btnTestP = new Button(this);
        btnTestP.setText("测试推送");
        btnTestP.setLayoutParams(new LinearLayout.LayoutParams(0, dp(44), 1f));
        btnTestP.setOnClickListener(v -> testPush());
        rowP.addView(btnTestP);
        cPush.addView(rowP);

        root.addView(cPush);
        loadNotify(spType, etHook, spTpl, etTpl);
        loadMail(etHost, etPort, chkSsl, etUser, etPass, etTo);

        // ---------- 日志卡 ----------
        LinearLayout cLog = card();
        TextView logTitle = new TextView(this);
        logTitle.setText("执行日志");
        logTitle.setTextSize(13);
        logTitle.setTextColor(0xFF52606D);
        cLog.addView(logTitle);

        tvLog = new TextView(this);
        tvLog.setBackground(solid(0xFF101822, 10));
        tvLog.setTextColor(0xFF9FE08A);
        tvLog.setTextSize(11);
        tvLog.setPadding(dp(10), dp(10), dp(10), dp(10));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(8), 0, 0);
        tvLog.setLayoutParams(lp);
        tvLog.setText("版本 " + APP_VER + " · 构建 " + BUILD_TS + "\n签名已固定，后续可直接覆盖安装，无需卸载。\n就绪。\n");
        cLog.addView(tvLog);
        root.addView(cLog);

        btnSend.setOnClickListener(v -> doSend());
        btnLogin.setOnClickListener(v -> doLogin());
        btnCopy.setOnClickListener(v -> {
            if (TextUtils.isEmpty(lastToken)) return;
            copy(lastToken);
        });
        btnFold.setOnClickListener(v -> {
            tokExpanded = !tokExpanded;
            updateTokView();
        });
        loadHist();
    }

    private GradientDrawable grad(int[] colors, int rDp) {
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR, colors);
        g.setCornerRadius(dp(rDp));
        return g;
    }

    private GradientDrawable solid(int fill, int rDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(rDp));
        return g;
    }

    private LinearLayout card() {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable g = solid(0xFFFFFFFF, 16);
        g.setStroke(1, 0xFFE3E9F2);
        c.setBackground(g);
        c.setPadding(dp(14), dp(14), dp(14), dp(14));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.setMargins(0, dp(12), 0, 0);
        c.setLayoutParams(p);
        return c;
    }

    private StateListDrawable pressable(int[] normal, int[] pressed, int rDp) {
        StateListDrawable s = new StateListDrawable();
        s.addState(new int[]{android.R.attr.state_pressed}, grad(pressed, rDp));
        s.addState(new int[]{-android.R.attr.state_enabled}, solid(0xFFBFC7D2, rDp));
        s.addState(new int[]{}, grad(normal, rDp));
        return s;
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
        e.setPadding(dp(14), dp(12), dp(14), dp(12));
        GradientDrawable g = solid(0xFFF7F9FC, 12);
        g.setStroke(1, 0xFFDCE3EE);
        e.setBackground(g);
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
        tokExpanded = false;
        updateTokView();
        saveHist(phone, token);
        tvLog.append("✓ 令牌已获取，手机号 " + phone + "\n");
        toast("成功，点「复制令牌」即可复制完整令牌");
        // 配了 webhook 就顺带推一条通知（没配则静默跳过）
        try { pushAfterToken(phone, expireDays(token)); } catch (Exception ignored) { }
    }

    // ---------- 令牌显示：默认折叠摘要，点展开才显示长串 ----------
    private void updateTokView() {
        String t = lastToken == null ? "" : lastToken;
        if (tokExpanded) {
            tvTok.setText(t);
            btnFold.setText("收起");
        } else {
            String head = t.length() > 24 ? t.substring(0, 24) : t;
            tvTok.setText(head + "…\n（共 " + t.length() + " 字符，点右侧「展开」查看完整，点「复制令牌」直接复制）");
            btnFold.setText("展开完整令牌");
        }
    }

    // ---------- 历史：令牌在本机 AES 加密保存 ----------
    private byte[] localKey() {
        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        String b64 = sp.getString(EKEY_KEY, "");
        if (b64 == null || b64.isEmpty()) {
            byte[] k = new byte[16];
            new SecureRandom().nextBytes(k);
            sp.edit().putString(EKEY_KEY, Base64.encodeToString(k, Base64.NO_WRAP)).apply();
            return k;
        }
        return Base64.decode(b64, Base64.DEFAULT);
    }

    private String encLocal(String plain) {
        try {
            byte[] iv = new byte[16];
            new SecureRandom().nextBytes(iv);
            Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
            c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(localKey(), "AES"), new IvParameterSpec(iv));
            byte[] ct = c.doFinal(plain.getBytes("UTF-8"));
            byte[] out = new byte[iv.length + ct.length];
            System.arraycopy(iv, 0, out, 0, iv.length);
            System.arraycopy(ct, 0, out, iv.length, ct.length);
            return Base64.encodeToString(out, Base64.NO_WRAP);
        } catch (Throwable e) { return ""; }
    }

    private String decLocal(String enc) {
        try {
            byte[] all = Base64.decode(enc, Base64.DEFAULT);
            if (all.length <= 16) return "";
            byte[] iv = new byte[16], ct = new byte[all.length - 16];
            System.arraycopy(all, 0, iv, 0, 16);
            System.arraycopy(all, 16, ct, 0, ct.length);
            Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(localKey(), "AES"), new IvParameterSpec(iv));
            return new String(c.doFinal(ct), "UTF-8");
        } catch (Throwable e) { return ""; }
    }

    private void loadHist() {
        histCache.clear();
        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        String raw = sp.getString(HIST_KEY, "");
        if (raw == null || raw.isEmpty()) { renderHist(); return; }
        for (String line : raw.split("\n")) {
            if (line.isEmpty()) continue;
            String[] f = line.split("\t", -1);
            if (f.length < 3) continue;
            histCache.add(new String[]{f[0], f[1], f[2]});   // phone, 加密令牌, 时间戳
        }
        renderHist();
    }

    private void saveHist(String phone, String token) {
        for (int i = 0; i < histCache.size(); i++) {
            if (histCache.get(i)[0].equals(phone)) { histCache.remove(i); break; }
        }
        histCache.add(0, new String[]{phone, encLocal(token), String.valueOf(System.currentTimeMillis())});
        if (histCache.size() > 20) histCache = new ArrayList<>(histCache.subList(0, 20));
        persistHist();
        renderHist();
    }

    private void persistHist() {
        StringBuilder sb = new StringBuilder();
        for (String[] r : histCache) {
            if (sb.length() > 0) sb.append("\n");
            sb.append(r[0]).append("\t").append(r[1]).append("\t").append(r[2]);
        }
        getSharedPreferences("cfg", MODE_PRIVATE).edit().putString(HIST_KEY, sb.toString()).apply();
    }

    private String mask(String phone) {
        if (phone == null) return "";
        if (phone.length() == 11) return phone.substring(0, 3) + "****" + phone.substring(7);
        return phone.length() > 4 ? phone.substring(0, phone.length() - 4) + "****" : phone;
    }

    private String fmtTs(String ms) {
        try {
            long v = Long.parseLong(ms);
            java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("MM-dd HH:mm", java.util.Locale.CHINA);
            return f.format(new java.util.Date(v));
        } catch (Throwable e) { return ""; }
    }

    private void renderHist() {
        histList.removeAllViews();
        if (histCache.isEmpty()) {
            TextView e = new TextView(this);
            e.setText("暂无记录。登录成功后会自动存到这里。");
            e.setTextSize(12);
            e.setTextColor(0xFF9AA7B6);
            e.setPadding(0, dp(6), 0, dp(6));
            histList.addView(e);
            return;
        }
        for (int i = 0; i < histCache.size(); i++) {
            final String[] r = histCache.get(i);
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.VERTICAL);
            GradientDrawable g = solid(0xFFF7F9FC, 12);
            g.setStroke(1, 0xFFE1E8F2);
            row.setBackground(g);
            row.setPadding(dp(12), dp(10), dp(12), dp(10));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.setMargins(0, dp(8), 0, 0);
            row.setLayoutParams(lp);

            TextView p1 = new TextView(this);
            p1.setText(mask(r[0]));
            p1.setTextSize(15);
            p1.setTypeface(null, Typeface.BOLD);
            p1.setTextColor(0xFF22303F);
            row.addView(p1);

            TextView p2 = new TextView(this);
            p2.setText("获取于 " + fmtTs(r[2]));
            p2.setTextSize(11);
            p2.setTextColor(0xFF8896A6);
            p2.setPadding(0, dp(2), 0, 0);
            row.addView(p2);

            final int idx = i;
            row.setOnClickListener(v -> {
                String t = decLocal(r[1]);
                if (TextUtils.isEmpty(t)) { toast("本机解密失败"); return; }
                copy(t);
            });
            row.setOnLongClickListener(v -> {
                new AlertDialog.Builder(this)
                        .setTitle("删除这条记录")
                        .setMessage(mask(r[0]) + " · " + fmtTs(r[2]))
                        .setNegativeButton("取消", null)
                        .setPositiveButton("删除", (d, w) -> {
                            if (idx < histCache.size()) histCache.remove(idx);
                            persistHist();
                            renderHist();
                            toast("已删除");
                        })
                        .show();
                return true;
            });
            histList.addView(row);
        }
    }

    private void copy(String t) {
        ClipboardManager cmg = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (cmg != null) cmg.setPrimaryClip(ClipData.newPlainText("token", t));
        toast("已复制令牌（" + t.length() + " 字符）");
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

    // ---------- 推送：网页端受 CORS 限制无法直连钉钉/企微，改在 App 内发送 ----------
    private static final String[] TPL = {
            "### 移动云盘 \u00b7 每日签到\n{time}\n\n{rows}\n\n合计 +{sum}",
            "### 移动云盘 \u00b7 每日签到\n{time}\n\n{rows}\n\n合计 +{sum} \u00b7 正常 {ok}",
            "### \u26a0 云盘签到异常\n{time}\n\n{rows}",
            "云盘签到 {time}：{sum} 豆，{ok}",
            ""
    };

    private void saveNotify(int type, String url, int tpl, String custom) {
        getSharedPreferences("cfg", MODE_PRIVATE).edit()
                .putInt("push_type", type).putString("push_url", url)
                .putInt("push_tpl", tpl).putString("push_custom", custom).apply();
    }

    private void loadNotify(android.widget.Spinner spType, EditText etHook, android.widget.Spinner spTpl, EditText etTpl) {
        android.content.SharedPreferences s = getSharedPreferences("cfg", MODE_PRIVATE);
        spType.setSelection(s.getInt("push_type", 0));
        etHook.setText(s.getString("push_url", ""));
        int t = s.getInt("push_tpl", 0);
        spTpl.setSelection(t);
        etTpl.setText(s.getString("push_custom", t >= 0 && t < TPL.length ? TPL[t] : ""));
        etTpl.setVisibility(t == 4 ? android.view.View.VISIBLE : android.view.View.GONE);
    }

    private void importPushCfg(EditText etHook, EditText etTpl, android.widget.Spinner spType, android.widget.Spinner spTpl) {
        try {
            android.content.ClipboardManager cm = (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm == null || cm.getPrimaryClip() == null) { toast("剪贴板为空"); return; }
            String s = cm.getPrimaryClip().getItemAt(0).coerceToText(this).toString().trim();
            JSONObject j = new JSONObject(s);
            String url = j.optString("url", "");
            if (url.isEmpty()) { toast("配置里没有 webhook"); return; }
            String tpl = j.optString("tpl", "");
            String ty = j.optString("type", "dingtalk");
            etHook.setText(url);
            spType.setSelection("wecom".equals(ty) ? 1 : ("feishu".equals(ty) ? 2 : 0));
            int idx = 4;
            for (int i = 0; i < 4; i++) if (TPL[i].equals(tpl)) { idx = i; break; }
            spTpl.setSelection(idx);
            etTpl.setText(tpl);
            saveNotify(spType.getSelectedItemPosition(), url, idx, tpl);
            toast("已导入推送配置");
        } catch (Exception e) { toast("导入失败：" + e.getMessage()); }
    }

    private void testPush() {
        android.content.SharedPreferences s = getSharedPreferences("cfg", MODE_PRIVATE);
        final int type = s.getInt("push_type", 0);
        if (type == 3) {
            if (s.getString("smtp_user", "").trim().isEmpty()) { toast("请先填写邮箱账号"); return; }
        } else if (s.getString("push_url", "").isEmpty()) { toast("请先填写 webhook 地址"); return; }
        String body = renderTpl(s.getInt("push_tpl", 0), s.getString("push_custom", ""),
                "182****4895\u3000今日 +6\u3000总 307\n172****9953\u3000今日 +6\u3000总 2021", "12", "2/2");
        log("测试推送中…");
        final String subj = "【测试】云盘签到通知";
        pool.execute(() -> {
            String r = dispatchPush(subj, body);
            boolean ok = r.startsWith("OK");
            final String msg = ok ? "\u2713 推送成功，请查收" : "\u2717 推送失败：" + r;
            runOnUiThread(() -> log(msg, !ok));
        });
    }

    /** 按当前配置分发：3=邮件SMTP，其余=群机器人 webhook */
    private String dispatchPush(String subject, String text) {
        android.content.SharedPreferences s = getSharedPreferences("cfg", MODE_PRIVATE);
        int type = s.getInt("push_type", 0);
        if (type == 3) {
            String user = s.getString("smtp_user", "").trim();
            String host = s.getString("smtp_host", "").trim();
            if (user.isEmpty()) return "未填写邮箱账号";
            if (host.isEmpty()) return "未填写 SMTP 服务器";
            int port = s.getInt("smtp_port", 465);
            boolean ssl = s.getBoolean("smtp_ssl", true);
            String pass = s.getString("smtp_pass", "");
            String to = s.getString("mail_to", "").trim();
            if (to.isEmpty()) to = user;
            try {
                new SmtpSender().send(host, port, ssl, !ssl, user, pass, user, to, subject, text);
                return "OK";
            } catch (Exception e) { return String.valueOf(e.getMessage()); }
        }
        return sendPush(type, s.getString("push_url", ""), text);
    }

    private void saveMail(String host, int port, boolean ssl, String user, String pass, String to) {
        getSharedPreferences("cfg", MODE_PRIVATE).edit()
                .putString("smtp_host", host).putInt("smtp_port", port).putBoolean("smtp_ssl", ssl)
                .putString("smtp_user", user).putString("smtp_pass", pass).putString("mail_to", to).apply();
    }

    private void loadMail(EditText etHost, EditText etPort, android.widget.CheckBox chkSsl,
                          EditText etUser, EditText etPass, EditText etTo) {
        android.content.SharedPreferences s = getSharedPreferences("cfg", MODE_PRIVATE);
        etHost.setText(s.getString("smtp_host", ""));
        etPort.setText(String.valueOf(s.getInt("smtp_port", 465)));
        chkSsl.setChecked(s.getBoolean("smtp_ssl", true));
        etUser.setText(s.getString("smtp_user", ""));
        etPass.setText(s.getString("smtp_pass", ""));
        etTo.setText(s.getString("mail_to", ""));
    }

    private static int portOf(String v) {
        try { return Integer.parseInt(v.trim()); } catch (Exception e) { return 465; }
    }

    private String renderTpl(int idx, String custom, String rows, String sum, String ok) {
        String t = (idx == 4) ? custom : (idx >= 0 && idx < TPL.length ? TPL[idx] : TPL[0]);
        if (t == null || t.trim().isEmpty()) t = TPL[0];
        String time = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.CHINA).format(new java.util.Date());
        return t.replace("{time}", time).replace("{rows}", rows).replace("{sum}", sum).replace("{ok}", ok);
    }

    private String sendPush(int type, String url, String text) {
        try {
            String body;
            if (type == 1) body = "{\"msgtype\":\"markdown\",\"markdown\":{\"content\":" + jstr(text) + "}}";
            else if (type == 2) body = "{\"msgtype\":\"text\",\"content\":{\"text\":" + jstr(text) + "}}";
            else body = "{\"msgtype\":\"markdown\",\"markdown\":{\"title\":\"云盘签到\",\"text\":" + jstr(text) + "}}";
            Map<String, String> h = new HashMap<>();
            h.put("Content-Type", "application/json");
            Resp r = http(url, "POST", h, body, false);
            String b = r.body == null ? "" : r.body;
            if (r.code >= 200 && r.code < 300) {
                if (b.contains("errcode") && !b.replace(" ", "").contains("\"errcode\":0")) return "接口返回 " + safe(b, 120);
                return "OK";
            }
            return "HTTP " + r.code + " " + safe(b, 120);
        } catch (Exception e) { return String.valueOf(e.getMessage()); }
    }

    private static String jstr(String s) {
        if (s == null) return "\"\"";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"') b.append("\\\"");
            else if (c == '\\') b.append("\\\\");
            else if (c == '\n') b.append("\\n");
            else if (c == '\r') b.append("\\r");
            else if (c == '\t') b.append("\\t");
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append("\"").toString();
    }

    /** 抓到令牌后按配置推一条通知（没配 webhook 则静默跳过） */
    private void pushAfterToken(String phone, String days) {
        android.content.SharedPreferences s = getSharedPreferences("cfg", MODE_PRIVATE);
        final int type = s.getInt("push_type", 0);
        boolean has = (type == 3) ? !s.getString("smtp_user", "").trim().isEmpty()
                : !s.getString("push_url", "").isEmpty();
        if (!has) return;
        String time = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.CHINA).format(new java.util.Date());
        String text = (type == 3)
                ? ("云盘令牌已更新\n\n" + mask(phone) + " \u00b7 剩余 " + days + " 天\n\n" + time)
                : ("### 云盘令牌已更新\n" + time + "\n\n" + mask(phone) + " \u00b7 剩余 " + days + " 天");
        final String subj = "云盘令牌已更新 \u00b7 " + mask(phone);
        pool.execute(() -> {
            String r = dispatchPush(subj, text);
            boolean ok = r.startsWith("OK");
            runOnUiThread(() -> log(ok ? "\u2713 已推送令牌更新通知" : "\u2717 通知推送失败：" + r, !ok));
        });
    }

    private static String expireDays(String token) {
        try {
            String dec = new String(Base64.decode(token.trim(), Base64.DEFAULT), "UTF-8");
            String[] ps = dec.split("\\|");
            if (ps.length >= 4) {
                long exp = Long.parseLong(ps[3].trim());
                long d = Math.round((exp - System.currentTimeMillis()) / 86400000.0 * 10) / 10;
                return String.valueOf(d);
            }
        } catch (Exception ignored) { }
        return "未知";
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
