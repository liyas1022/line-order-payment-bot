# LINE 訂單與付款 Bot｜求職作品摘要

> 本文件是為「AI 流程自動化助理工程師」整理的作品介紹。此專案為模擬付款展示版，不是過去商業營運系統的完整原始碼。

**專案連結：** https://github.com/liyas1022/line-order-payment-bot  
**主要技術：** Python、Flask、LINE Messaging API、Webhook、SQLite、JSON、GitHub Actions  
**可驗證範圍：** GitHub 原始碼、系統架構、六個測試方法與自動化測試紀錄。

## 01｜解決什麼問題

將訂單通道選擇、建立訂單、付款狀態通知與查單整合到 LINE 聊天室，減少不同畫面之間的人工切換。本作品以模擬資料重現流程，方便展示和測試，不會產生真實付款。

## 02｜已實作的展示功能

- `/模式` 選單及 `/速1`、`/速2`、`/速3` 三種通道模式，個人設定保存到 SQLite。
- 輸入 `+300` 等金額建立測試訂單，回覆 LINE Flex Message 訂單卡片。
- 查詢自己的訂單與最近紀錄；隔離不同 LINE 使用者的訂單資料。
- 接收並驗證 LINE Webhook HMAC-SHA256 簽章；防止重送同一事件時重複開單。
- 以模擬付款與 Callback 推進訂單狀態，處理金額／狀態驗證及通知重試。
- 透過 Python unittest 與 GitHub Actions 執行自動化測試。

## 03｜系統主要流程

LINE 使用者 → LINE Messaging API → Flask Webhook（簽章驗證）→ 訂單／模式處理 → SQLite → LINE Flex Message 回覆。模擬付款 Callback 會驗證請求、更新訂單狀態，必要時推送新狀態卡片。

## 04｜對應職缺需求

| 職缺能力 | 作品中的證據 |
|---|---|
| API / Webhook 串接 | `app.py` 的 LINE Webhook、Reply API、Push API 與 Callback |
| 資料庫 | SQLite 訂單、使用者模式、Webhook 事件與通知資料 |
| 系統測試 | `tests/test_line_bot.py` 的六個測試案例、GitHub Actions |
| 錯誤追蹤與可靠性 | 簽章拒絕、事件去重、重複付款與通知重試 |
| AI 輔助開發 | 使用 AI 協助產生／修改程式，並以需求與實際測試迭代 |

## 05｜個人參與方式（務實呈現）

由我提出操作需求、整理訂單與通知流程、決定測試情境並檢查結果；程式碼主要透過 AI 協助產生與修改。這份作品展示的是我運用 AI 實作流程自動化及系統整合的能力，**不代表我能在不使用 AI 的情況下獨立完成所有程式碼**。

## 06｜驗證與限制

- 本機測試指令：`python -m unittest discover -s tests -v`。
- 最近一次 GitHub Actions（2026-11-06 台灣時間）結果：**成功**。可至儲存庫 Actions 查看詳細紀錄。
- 展示版本使用 **Mock Payment Service**，沒有串接真實銀行、支付平台或實際金流。
- `docs/assets/flex-preview.svg` 是由範例 JSON 產生的結構預覽，不是 LINE 實機截圖。
- 沒有在此作品中宣稱真實交易量、節省多少工時或處理能力等尚未驗證的績效數字。

## 07｜面試時可以開啟的檔案

- [README.md](https://github.com/liyas1022/line-order-payment-bot/blob/main/README.md)：執行步驟與功能介紹。
- [app.py](https://github.com/liyas1022/line-order-payment-bot/blob/main/app.py)：Flask、Webhook、訂單與 Callback。
- [docs/architecture.md](https://github.com/liyas1022/line-order-payment-bot/blob/main/docs/architecture.md)：系統架構與設計取捨。
- [tests/test_line_bot.py](https://github.com/liyas1022/line-order-payment-bot/blob/main/tests/test_line_bot.py)：測試案例。
- [GitHub Actions](https://github.com/liyas1022/line-order-payment-bot/actions)：測試執行結果。

**備註：** 我過去另有實際投入營運的 LINE 訂單自動化經歷；與此公開展示專案分開陳述，避免將模擬功能誤稱為真實商業金流。
