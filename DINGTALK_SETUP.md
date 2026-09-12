# 📮 接入你自己的钉钉机器人

> 本项目已开源。任何人 fork 后，都可以填入**自己的**钉钉机器人，
> 把资费变化推送到**自己的**钉钉群里。
>
> 你填的密钥只存在你自己的仓库里，**作者和其他人都看不到**。

---

## 三步搞定

### 第 1 步：创建钉钉机器人

1. 打开你要接收推送的**钉钉群** → 右上角「群设置」→「智能群助手」
2. 点「添加机器人」→ 选「自定义（通过 Webhook 接入自定义服务）」
3. 安全设置**建议勾选「加签」**（多一层保护，强烈推荐）
4. 创建后你会拿到两个东西：

   | 名称 | 长什么样 | 用在哪 |
   |---|---|---|
   | **Webhook 地址** | `https://oapi.dingtalk.com/robot/send?access_token=xxxx` | 填 `DINGTALK_WEBHOOK` |
   | **加签密钥** | `SECxxxxxxxx`（勾选加签才有） | 填 `DINGTALK_SECRET` |

   ⚠️ 页面关掉后就看不到了，先复制下来。

---

### 第 2 步：填进你的仓库（两种方式，选一个）

#### 方式 A：GitHub Actions 云端定时推送（推荐，全自动）

1. **Fork 本仓库**到你自己的账号
2. 进入你的仓库 → **Settings** → **Secrets and variables** → **Actions**
3. 点 **New repository secret**，依次添加：

   | Name | Secret |
   |---|---|
   | `DINGTALK_WEBHOOK` | 第 1 步的 Webhook 地址 |
   | `DINGTALK_SECRET` | 第 1 步的加签密钥（没开加签可留空） |

   可选（不填就用默认值）：

   | Name | 作用 | 默认值 |
   |---|---|---|
   | `FOCUS_SEC` | 明细列哪个省份，如 `guangdong` | `hunan` |
   | `SITE_URL` | 消息末尾的站点链接 | 本项目 Pages 地址 |

4. 打开 **Actions** 页 → 左侧选 **Tariff Summary to DingTalk** → **Run workflow**
5. **约 14 秒后**，你的钉钉群就会收到汇总消息 ✅

> 🔒 Secrets 是加密存储且**只写不读**——存进去后连你自己都看不到原文，
> 运行时自动注入，日志里显示为 `***`，不会泄露。

#### 方式 B：本地运行（临时试一下 / 自己的服务器）

```bash
git clone https://github.com/<你的用户名>/hunan-tariff-site.git
cd hunan-tariff-site
cp .env.example .env
# 编辑 .env，填入你的 Webhook 和加签密钥
python3 scripts/dingtalk_summary.py --test    # 先发一条测试消息
python3 scripts/dingtalk_summary.py           # 正式推送
```

`.env` 已在 `.gitignore` 里，不会被提交上去。

---

### 第 3 步：验证

运行测试命令：

```bash
python3 scripts/dingtalk_summary.py --test
```

钉钉群收到「✅ 配置成功」就说明通了。它会告诉你加签有没有配上、关注哪个省。

如果失败，看下面「常见问题」。

---

## 推送长什么样

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

明细只列你关注的那一个省份，其余不展示。

---

## 自动推送时间

默认每天两次（北京时间 **10:00** 和 **20:00**），各统计前 24 小时。

想改时间在 `.github/workflows/dingtalk-summary.yml` 里调 cron：

```yaml
schedule:
  - cron: "0 2 * * *"     # 北京 10:00
  - cron: "0 12 * * *"    # 北京 20:00
```

> GitHub Actions 用的是 UTC，北京时间减 8 小时。

---

## 常见问题

**Q：收不到消息？**
- 先跑 `--test` 确认配置对不对
- 检查 Actions 是否运行成功（绿勾）
- 没开加签的话，安全设置可能是「自定义关键词」——那你的消息里必须包含那个关键词

**Q：提示「签名不匹配」？**
- 加签密钥填错了，回钉钉机器人页面重新复制
- 注意是 `SEC` 开头那串，不是 Webhook 地址

**Q：我只关心某个省？**
- 在 Secrets 里加 `FOCUS_SEC`，值填拼音，如 `guangdong`、`zhejiang`、`beijing`

**Q：密钥会被别人看到吗？**
- 不会。Secrets 加密存储、只写不读，日志自动脱敏。
- 你的 fork 仓库里，Secrets 只有你自己的 workflow 能读到。

**Q：不配钉钉会怎样？**
- 抓取照常运行，只是不推送。站点数据一样更新。

---

## 安全建议

1. **务必开启加签** —— 即使 Webhook 地址泄露，没有加签密钥也推不了
2. **不要**把密钥写进代码或提交到仓库
3. 公开仓库建议开启「Require approval for all outside collaborators」
   （Settings → Actions → Fork pull request workflows），
   防止他人通过 PR 改动 workflow 窃取 Secrets
