package com.nexio.yuntok;

import android.util.Base64;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;

import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/**
 * 极简 SMTP 客户端：不依赖任何第三方库，纯 Socket 实现。
 * 支持 465 直连 SSL 与 587 STARTTLS 两种方式，AUTH LOGIN 认证。
 */
public class SmtpSender {

    private Socket sock;
    private BufferedReader in;
    private OutputStream out;

    /**
     * @param ssl       true=直连 SSL（一般 465），false=明文连接
     * @param starttls  ssl 为 false 时是否升级 STARTTLS（一般 587）
     */
    public void send(String host, int port, boolean ssl, boolean starttls,
                     String user, String pass, String from, String to,
                     String subject, String body) throws Exception {
        try {
            if (ssl) {
                sock = ((SSLSocketFactory) SSLSocketFactory.getDefault()).createSocket(host, port);
            } else {
                sock = new Socket();
                sock.connect(new InetSocketAddress(host, port), 20000);
            }
            sock.setSoTimeout(25000);
            attach();

            expect(readResp(), "220", "连接服务器");
            expect(cmd("EHLO yuntok"), "250", "EHLO");

            if (!ssl && starttls) {
                expect(cmd("STARTTLS"), "220", "STARTTLS");
                SSLSocket s = (SSLSocket) ((SSLSocketFactory) SSLSocketFactory.getDefault())
                        .createSocket(sock, host, port, true);
                s.startHandshake();
                sock = s;
                attach();
                expect(cmd("EHLO yuntok"), "250", "EHLO(TLS)");
            }

            expect(cmd("AUTH LOGIN"), "334", "请求认证");
            expect(cmd(b64(user)), "334", "邮箱账号");
            String r = cmd(b64(pass));
            if (!r.startsWith("235")) throw new Exception("授权码/密码被拒绝：" + r);

            expect(cmd("MAIL FROM:<" + from + ">"), "250", "发件人");
            expect(cmd("RCPT TO:<" + to + ">"), "250", "收件人");
            expect(cmd("DATA"), "354", "开始投递");

            out.write(buildMsg(from, to, subject, body).getBytes("UTF-8"));
            out.flush();
            expect(readResp(), "250", "投递");
            try { cmd("QUIT"); } catch (Exception ignored) { }
        } finally {
            close();
        }
    }

    private void attach() throws Exception {
        in = new BufferedReader(new InputStreamReader(sock.getInputStream(), "UTF-8"));
        out = sock.getOutputStream();
    }

    /** 读取一次完整响应（含多行），返回最后一行 */
    private String readResp() throws Exception {
        String line = in.readLine();
        if (line == null) throw new Exception("服务器主动关闭了连接");
        while (line.length() >= 4 && line.charAt(3) == '-') {
            String next = in.readLine();
            if (next == null) break;
            line = next;
        }
        return line;
    }

    private String cmd(String c) throws Exception {
        out.write((c + "\r\n").getBytes("UTF-8"));
        out.flush();
        return readResp();
    }

    private static void expect(String resp, String code, String what) throws Exception {
        if (resp == null || !resp.startsWith(code))
            throw new Exception(what + " 失败：" + (resp == null ? "无响应" : resp));
    }

    private static String b64(String s) {
        return Base64.encodeToString(s.getBytes(java.nio.charset.Charset.forName("UTF-8")), Base64.NO_WRAP);
    }

    /** 中文主题与正文都用 base64 编码，避免乱码 */
    private static String buildMsg(String from, String to, String subject, String body) {
        StringBuilder sb = new StringBuilder();
        sb.append("From: <").append(from).append(">\r\n");
        sb.append("To: <").append(to).append(">\r\n");
        sb.append("Subject: =?UTF-8?B?").append(b64(subject)).append("?=\r\n");
        sb.append("MIME-Version: 1.0\r\n");
        sb.append("Content-Type: text/plain; charset=UTF-8\r\n");
        sb.append("Content-Transfer-Encoding: base64\r\n");
        sb.append("Date: ").append(new java.text.SimpleDateFormat(
                "EEE, d MMM yyyy HH:mm:ss Z", java.util.Locale.US).format(new java.util.Date())).append("\r\n");
        sb.append("\r\n");
        String enc = b64(body);
        for (int i = 0; i < enc.length(); i += 76) {
            sb.append(enc, i, Math.min(i + 76, enc.length())).append("\r\n");
        }
        sb.append(".\r\n");
        return sb.toString();
    }

    private void close() {
        try { if (in != null) in.close(); } catch (Exception ignored) { }
        try { if (out != null) out.close(); } catch (Exception ignored) { }
        try { if (sock != null) sock.close(); } catch (Exception ignored) { }
    }
}
