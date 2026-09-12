# 📮 接入你自己的通知通道（钉钉 / 飞书 / 企业微信 / 邮件）

> 本项目已开源。任何人 fork 后，填入**自己的**凭据，
> 资费变化就能推送到**自己的**钉钉 / 飞书 / 企业微信 / 邮箱。
>
> 你填的密钥只存在你自己的仓库里，**作者和其他人都看不到**。
> 四个通道可任意组合：配几个就推几个，没配的自动跳过。

---

## 一、填在哪里

### 方式 A：GitHub Actions 云端（推荐，全自动）

1. **Fork 本仓库**
2. **Settings → Secrets and variables → Actions → New repository secret**
3. 按需添加下表的变量（**只填你要用的通道**）
4. **Actions** → 选 **Tariff Notify** → **Run workflow** → 约 14 秒后收到

> 🔒 Secrets 加密存储、**只写不读**——存进去后连你自己都看不到原文，
> 运行时自动注入，日志里显示为 `***`。

### 方式 B：本地 / 自己的服务器

```bash
git clone https://github.com/<你的用户名>/hunan-tariff-site.git
cd hunan-tariff-site
cp .env.example .env
# 编辑 .env 填入你的凭据（.env 已被 .gitignore 排除，不会误提交）
python3 scripts/notify.py --test      # 测试所有已配置通道
python3 scripts/dingtalk_summary.py   # 正式推送汇总
```

---

## 二、四个通道怎么拿凭据

### 🔵 钉钉机器人

1. 钉钉群 →「群设置」→「智能群助手」→「添加机器人」→「自定义」
2. 安全设置**建议勾选「加签」**
3. 拿到 Webhook 地址与加签密钥（`SEC` 开头）

| Secret | 值 |
|---|---|
| `DINGTALK_WEBHOOK` | `https://oapi.dingtalk.com/robot/send?access_token=xxx` |
| `DINGTALK_SECRET` | `SECxxx`（没开加签可留空） |

---

### 🟦 飞书机器人

1. 飞书群 →「设置」→「群机器人」→「添加机器人」→「自定义机器人」
2. 安全设置可设「签名校验」
3. 拿到 Webhook 地址与签名密钥

| Secret | 值 |
|---|---|
| `FEISHU_WEBHOOK` | `https://open.feishu.cn/open-apis/bot/v2/hook/xxx` |
| `FEISHU_SECRET` | 签名密钥（没开可留空） |

> 飞书以**卡片消息**推送，支持 Markdown 渲染。

---

### 🟩 企业微信机器人

1. 企业微信群 → 右上角「…」→「群机器人」→「添加」
2. 直接复制 Webhook 地址（企业微信机器人无加签，靠地址本身保密）

| Secret | 值 |
|---|---|
| `WECOM_WEBHOOK` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx` |

> 内容超长时会自动降级为纯文本，避免被接口拒绝。

---

### 📧 邮件（SMTP）

以 QQ 邮箱为例：设置 → 账户 → 开启 **SMTP 服务** → 生成**授权码**（不是登录密码）。

| Secret | 值 | 示例 |
|---|---|---|
| `SMTP_HOST` | SMTP 服务器 | `smtp.qq.com` |
| `SMTP_PORT` | 端口 | `465`（SSL）/ `587`（STARTTLS） |
| `SMTP_USER` | 发件邮箱 | `123456@qq.com` |
| `SMTP_PASS` | **授权码** | `abcdefghijklmnop` |
| `MAIL_TO` | 收件人，多个用逗号 | `a@qq.com,b@163.com` |
| `MAIL_FROM` | 发件人显示（可选，默认同 `SMTP_USER`） | |
| `MAIL_FROM_NAME` | 发件人名称（可选） | `资费监控` |

常用 SMTP：

| 邮箱 | Host | Port |
|---|---|---|
| QQ | `smtp.qq.com` | 465 |
| 163 | `smtp.163.com` | 465 |
| Gmail | `smtp.gmail.com` | 587 |
| Outlook | `smtp.office365.com` | 587 |

> 邮件同时发送**纯文本 + HTML** 两个版本，手机上排版正常。

---

## 三、通用可选项

| Secret | 作用 | 默认 |
|---|---|---|
| `FOCUS_SEC` | 明细只列哪个省（拼音） | `hunan` |
| `SITE_URL` | 消息末尾的站点链接 | 本项目 Pages |
| `SINCE_HOURS` | 统计最近 N 小时 | `24` |

省份拼音示例：`guangdong`、`zhejiang`、`beijing`、`hunan`、`quanguo`（全网）

---

## 四、验证

```bash
python3 scripts/notify.py --test
```

输出类似：

```
  ✅ 钉钉：errcode=0 ok
  ⏭  飞书：未配置（FEISHU_WEBHOOK 为空），跳过
  ⏭  企业微信：未配置（WECOM_WEBHOOK 为空），跳过
  ❌ 邮件：[Errno 110] Connection timed out

测试完成：成功 1 / 已配置 2（钉钉）
```

云端则直接跑 **Actions → Tariff Notify → Run workflow**，看日志里同样的输出。

---

## 五、推送长什么样

```
## 资费变化汇总

**统计范围**：09-12 16:27 ~ 09-13 16:27 (北京时间)

- 🔵 移动：新增 340、下架 284、修改 1196
  - 湖南：无变化
- 🟠 联通：无变化
- 🟢 电信：新增 7、下架 8、修改 0
  - 湖南：新增7 下架8 修改0
- 🟣 广电：新增 5、下架 1、修改 1
  - 湖南：无变化

**合计**：新增 352、下架 293、修改 1197

🔗 查看完整资费站
```

---

## 六、自动推送时间

默认每天两次（北京 **10:00** / **20:00**），各统计前 24 小时。
改时间编辑 `.github/workflows/dingtalk-summary.yml`：

```yaml
schedule:
  - cron: "0 2 * * *"     # 北京 10:00（UTC + 8）
  - cron: "0 12 * * *"    # 北京 20:00
```

---

## 七、常见问题

**Q：收不到？**
先跑 `--test` 看具体报错。钉钉若用「自定义关键词」安全设置，消息里必须含那个关键词。

**Q：签名不匹配？**
钉钉/飞书的密钥填错了。注意飞书是「签名校验」里那串，钉钉是 `SEC` 开头那串，两者算法不同、别混用。

**Q：邮件发不出？**
- 用的是**授权码**不是登录密码
- 465 配 SSL、587 配 STARTTLS，别混
- 部分邮箱需在设置里单独开启 SMTP

**Q：密钥会被看到吗？**
不会。Secrets 只写不读、日志脱敏；脚本本身**不含任何硬编码凭据**（全走环境变量）。

**Q：都不配会怎样？**
抓取照常，只是不推送，站点数据一样更新。

---

## 八、安全建议

1. 钉钉/飞书**开启加签**
2. 不要把密钥写进代码或提交 `.env`
3. 公开仓库开启 **Settings → Actions → Fork pull request workflows →
   Require approval for all outside collaborators**，
   防止他人通过 PR 改动 workflow 窃取 Secrets
