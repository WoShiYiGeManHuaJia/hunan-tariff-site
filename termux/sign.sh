#!/bin/sh
# 中国移动 10086 每日签到（手机端常驻版）
# 用法：sh ~/cmcc/sign.sh          前台跑（每天 09:00 / 20:00 各签一次）
#      nohup sh ~/cmcc/sign.sh &   后台常驻（推荐）
# 凭证放 ~/cmcc/cookie.txt

DIR="$HOME/cmcc"
mkdir -p "$DIR"
CK="$DIR/cookie.txt"
LOG="$DIR/sign.log"
DONE="$DIR/.done"
UA='Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
URL='https://wx.10086.cn/qwhdhub/qwhdmark/1021122301'

today() { TZ='CST-8' date +%Y%m%d; }
now()   { TZ='CST-8' date '+%Y-%m-%d %H:%M:%S'; }

sign_once() {
  D=$(today)
  if [ ! -s "$CK" ]; then
    echo "$(now) [跳过] 没有凭证：$CK" >> "$LOG"
    return
  fi
  CKV=$(tr -d '\r\n' < "$CK")

  # 1) 查今日状态
  R=$(curl -s --max-time 25 -X POST \
    -H "User-Agent: $UA" -H "Cookie: $CKV" \
    -H "Content-Type: application/json;charset=UTF-8" \
    -H "Origin: https://wx.10086.cn" -H "Referer: $URL" \
    -H "login-check: 1" -H "x-requested-with: XMLHttpRequest" \
    "https://wx.10086.cn/qwhdhub/api/mark/mark31/markstatus" -d '{}')

  case "$R" in
    *GOTO_LOGIN*)
      echo "$(now) [失败] 凭证失效，需要重新导出" >> "$LOG"
      return ;;
  esac

  # 今天是否已签（status=1）
  if echo "$R" | grep -q "\"date\":\"$D\"" && echo "$R" | grep -q '"status":"1"'; then
    echo "$(now) [已签] $D 今天已经签过了" >> "$LOG"
    echo "$D" > "$DONE"
    return
  fi

  # 2) 未签 -> 签到
  K=$(curl -s --max-time 25 -X POST \
    -H "User-Agent: $UA" -H "Cookie: $CKV" \
    -H "Content-Type: application/json;charset=UTF-8" \
    -H "Origin: https://wx.10086.cn" -H "Referer: $URL" \
    -H "login-check: 1" -H "x-requested-with: XMLHttpRequest" \
    "https://wx.10086.cn/qwhdhub/api/mark/mark31/domark" -d "{\"date\":\"$D\"}")

  echo "$(now) [签到] $D -> $K" | cut -c1-300 >> "$LOG"

  # 3) 回读确认
  sleep 2
  R2=$(curl -s --max-time 25 -X POST \
    -H "User-Agent: $UA" -H "Cookie: $CKV" \
    -H "Content-Type: application/json;charset=UTF-8" \
    -H "Origin: https://wx.10086.cn" -H "Referer: $URL" \
    -H "login-check: 1" -H "x-requested-with: XMLHttpRequest" \
    "https://wx.10086.cn/qwhdhub/api/mark/mark31/markstatus" -d '{}')
  if echo "$R2" | grep -q "\"date\":\"$D\"" && echo "$R2" | grep -q '"status":"1"'; then
    echo "$(now) [成功] $D 签到完成" >> "$LOG"
    echo "$D" > "$DONE"
  else
    echo "$(now) [未确认] $D 回读：$(echo "$R2" | cut -c1-200)" >> "$LOG"
  fi
}

echo "$(now) ==== 签到脚本启动 ====" >> "$LOG"
sign_once   # 启动时先签一次，方便你立刻看结果

while true; do
  H=$(TZ='CST-8' date +%H%M)
  D=$(today)
  case "$H" in
    0900|2000)
      if [ "$(cat "$DONE" 2>/dev/null)" != "$D" ]; then
        sign_once
      fi ;;
  esac
  sleep 55
done
