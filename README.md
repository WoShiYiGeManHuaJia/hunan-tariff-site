# 运营商资费监控 · 数据展示站（移动 / 联通 / 电信 / 广电）

本仓库是 **Hunan-Mobile-Billing-Monitoring（私有监控仓）** 的**公开数据展示层**，
仅包含从各运营商官网抓取的公开资费数据与静态展示页面，**不含任何代码密钥**。

## 在线访问

- 合集入口：<https://woshiyigemanhuajia.github.io/hunan-tariff-site/hub/>
- 中国移动：<https://woshiyigemanhuajia.github.io/hunan-tariff-site/>
- 中国联通：<https://woshiyigemanhuajia.github.io/hunan-tariff-site/unicom/>
- 中国电信：<https://woshiyigemanhuajia.github.io/hunan-tariff-site/telecom/>
- 中国广电：<https://woshiyigemanhuajia.github.io/hunan-tariff-site/gb/>

## 数据说明

- **移动**：全网资费（全国）+ 31 省，含套餐 / 加装包 / 营销活动 × 个人 / 政企 全分类
- **联通 / 广电**：全网 + 31 省；**电信**：湖南 + 全国
- 由私有监控仓的 GitHub Actions 定时抓取，自动同步到本仓库
- 数据均为各运营商官网公示的公开信息，仅供参考，办理业务请以营业厅官方信息为准

## 站点功能

省份切换与搜索、分类筛选、资费变化历史追踪、**CSV 导出**、**收藏关注**（保存在本机浏览器）。


---

## 📮 接入你自己的钉钉机器人

fork 本项目后，填入**你自己的**钉钉机器人，资费变化就能推送到**你的**钉钉群。

**完整教程见 → [DINGTALK_SETUP.md](DINGTALK_SETUP.md)**

三步速览：

1. 钉钉群里添加「自定义机器人」，拿到 **Webhook 地址**和**加签密钥**（建议勾选加签）
2. 进你的仓库 **Settings → Secrets and variables → Actions**，添加
   `DINGTALK_WEBHOOK` 和 `DINGTALK_SECRET`
3. Actions 里手动运行 **Tariff Summary to DingTalk**，约 14 秒后钉钉群收到汇总

推送示例：

```
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

> 🔒 你填的密钥只存在你自己的仓库里，加密存储且**只写不读**，作者与其他人都无法查看。
> 抓取脚本中**不包含任何凭据**（已扫描确认），全部通过环境变量注入。

## 自动化说明

抓取与推送均跑在 **GitHub Actions**（公开仓免费、不限量）：

| 工作流 | 频率（北京） | 说明 |
|---|---|---|
| `mobile-build.yml` | 08:47 / 20:47 | 移动抓取 + 站点构建 |
| `telecom-gb-fetch.yml` | 09:17 / 21:17 | 电信 + 广电抓取 |
| `unicom-fetch.yml` | 09:37 / 21:37 | 联通抓取（32 板块） |
| `dingtalk-summary.yml` | 10:00 / 20:00 | 钉钉汇总推送 |

fork 后如需停掉自动抓取，删除对应 workflow 文件即可。
