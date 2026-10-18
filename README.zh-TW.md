# ntu-course-announcements

用 command line抓 NTU Cool 的課程公告與課程檔案。

這個專案的起源是讀了 [`brianbbsu/NTU-Announcement-Crawler`](https://github.com/brianbbsu/NTU-Announcement-Crawler)，
然後發現它在現代 Python 上跑不起來。重寫成單一 ~700 行腳本，**只有一個**第三方依賴。

```bash
# 不用帳密 —— 先確認平台連不連得上
python3 scripts/ntu_fetch.py --probe

# 我這學期有哪些課
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
```

> English version: [README.md](README.md)

---

## 為什麼不直接用上游那份

上游專案是為 2019 年的 Python 版本寫的，帶著 Flask + SQLAlchemy + ORM service，
只為了讀一個 JSON endpoint。在 Python 3.14 上三處失敗：

```
ImportError: cannot import name 'Markup' from 'jinja2'          # Flask 1.0.2
AttributeError: module 'sqlite3.dbapi2' has no attribute 'version_info'   # SQLAlchemy 1.3.8
TypeError: Mapper.__init__() got an unexpected keyword argument 'order_by'
```

升級 Flask 會撞進 SQLAlchemy 的坑，SQLAlchemy 的坑再撞進 mapper API 被移除。
而**全部要改的地方只有一個檔案、四行** —— 這說明問題出在架構，不是版本號。

這個版本把 Flask、SQLAlchemy、`beautifulsoup4` 全部丟掉。
**唯一的第三方 import 是 `requests`。** HTML 解析改用標準庫的 `html.parser`，
因為真的需要 BeautifulSoup 的只有兩件事 —— 「找一個表單、讀它的 input」
跟「把可見文字攤平」—— 那就是二十行程式碼的 `HTMLParser`。

這**不是 fork**。上游專案沒有 LICENSE 檔，因此不能轉載 ——
本專案沒有從它複製任何程式碼，
從讀它的原始碼學到的東西都列在 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

---

## 安裝

當成指令用 —— 裝完 PATH 上會有 `ntu-cool`：

```bash
git clone <this-repo>
cd ntu-cool-announcements-skill
pipx install .          # 或：uv tool install .  /  python3 -m pip install --user .
ntu-cool --probe
```

模組叫 `ntu_fetch`，指令叫 `ntu-cool`，兩者做完全一樣的事 ——
`ntu-cool --help` 跟 `python3 scripts/ntu_fetch.py --help` 輸出相同。
看你要哪個；那個 script 根本不需要安裝就能跑。

需要 Python 3.9+ 與 `requests`。驗證：

```bash
ntu-cool --probe
```

### 測試

```bash
python3 -m unittest discover -s tests -v
```

41 個離線測試，不連網路、不用帳密。涵蓋 JSON 前綴處理、
不用 BeautifulSoup 的 HTML 表單解析、憑證檔權限防護，
以及最關鍵的一項 —— 藏在 `<head>` 的誘捕表單**永遠不會變成 POST 目標**。

### 備註

console script 是個薄薄的 wrapper：`ntu_fetch:main`，`main()` 回傳 exit code。
import 這個模組沒有任何副作用，所以測試可以 import 它而不會登入或連網。

> **用你真正會跑的那個 interpreter 測試。** venv 的 Python 和系統 Python 有各自獨立的
> `site-packages`。「import 失敗」的問題回報，有一半其實是在講錯的 interpreter。
> 詳見 `references/testing-and-interpreters.md`。

---

## 憑證

兩個平台需要你的 NTU 帳號。**這個工具不會儲存、不會索取、也不會印出密碼。**

方法一，在單一 shell 裡 export：

```bash
export NTU_USER=bXXXXXXXX
export NTU_PASS='...'
```

方法二（建議），放進一個檔案，腳本只在權限是 `600` 時才讀：

```bash
umask 077
echo '{"ntu_user":"bXXXXXXXX","ntu_pass":"..."}' > ~/.ntu-creds.json
```

權限太寬的憑證檔會被**直接拒絕**，並提示你用 `chmod` 修正。
另外注意：一個 terminal 裡 export 的環境變數，在另一個 terminal 是看不到的 ——
想讓這支腳本能無人值守跑（cron 之類），靠的是憑證檔，不是環境變數。

---

## 這個專案記住的三個坑

### 坑一：`/api/v1/courses` 不是你本學期的課表

它回傳的是這個帳號**過去曾經修過**的課。

```
API 回報：       10 門課，最新公告 2026-10-13，最舊 2025-09-05
                 → 漏掉 3 門本學期課程，其中一門是你的主修數學課
                 → 多 3 門已結束的課，以 {"access_restricted_by_date": true} 形式出現

登入後首頁回報：  7 門課，學期 "<term>"  ← 這個才對
```

所以 `fetch_courses()` 改成解析首頁裡夾帶的 JSON。
歷史名單還是可以用 `fetch_all_courses_historical()` 拿到 —— 當你要查上學期考試時間表的時候，
但**絕對不能拿它當本學期課表**。

### 坑二：教材不在公告正文裡

一學期實測：

```
20 則公告正文   6,658 字元   0 個檔案連結
課程 Files 樹   64 個檔案    91 MB
```

一則正文全文只有「attached」兩個字的公告，**不是**要回報「附件抓不到」的情況 ——
那是正常形狀，而且檔案完全抓得到。只讀公告就回報「這門課沒有附件」，
聽起來像個完整答案，實際上漏掉每一份習題。

### 坑三：檔案路徑要從物件裡讀，不要自己拼

```
GET /api/v1/courses/{id}/folders    → folder 物件
folder["files_url"]                 → 該資料夾裡的檔案
folder["folders_url"]               → 子資料夾；遞迴
```

猜了六個看起來很合理的路徑，全部 404 或 400 —— 包括
`/api/v1/courses/{id}/files`，那個看起來最對，而且是死的。
folder 物件自帶自己的 URL：**讀欄位**。

數任何東西之前先依 file `id` 去重。`/folders` 會在同一個清單裡同時回傳課程根資料夾
和它的子資料夾，所以遞迴寫得太直覺的話，會數出**110 個檔案，實際只有 64 個**。
`fetch_course_files()` 現在有做這件事；曾經有一版沒做，每個重複都回報了。
有一個測試會在它被拿掉時失敗。

公告附件是**第三組**，和前兩者都不同：某學期有 5 個，Files 樹有 64 個。
`--list-files` 和 `--download-files` 兩組都會收。

---

## 用法

### 公告

```bash
# 本學期課表
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json

# 單一課程的公告，直接印到畫面上
python3 scripts/ntu_fetch.py --course <COURSE> --since 2026-09-01 --stdout

# 寫成 markdown 進筆記目錄
python3 scripts/ntu_fetch.py --course <COURSE> --since 2026-09-01 --out ./captures/
```

### 課程檔案

```bash
# 列出 Files 樹裡的全部內容
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json

# 下載，跳過超過 20 MB 的檔案
python3 scripts/ntu_fetch.py --download-files --course <COURSE> \
    --cred-file ~/.ntu-creds.json --files-out ./files/ --max-mb 20
```

下載路徑是 `<files-out>/<course_id>/<file_id>/<檔名>`，
所以兩個同名檔案不會互相蓋掉。

---

## 這些輸出該信多少

| 說法 | 狀態 |
|---|---|
| NTU Cool 的 endpoint 還在 | 已驗證 —— 回 401 + 有結構的 body，不是 404 |
| SAML 登入流程正確 | 已對線上站台驗證過 |
| `/api/v1/courses` 是本學期課表 | **假的** —— 見坑一 |
| Files 樹的 endpoint 形狀 | 已驗證，列舉出 64 個檔案 |
| 下載到的真的 是 PDF | 每個檔案都做 magic bytes 檢查 |
| Ceiba 可達性 | **依網路而異** —— 見 `references/ceiba-unreachable.md` |
| Ceiba 爬蟲 | 沒實作；上游那個用位置參數解析表格的寫法未經驗證 |

**一個下載顯示 `OK`，代表兩道檢查都過了。** Cool 在簽名 URL 過期時，
會回 **HTTP 200 但內容是登入頁**，所以只看 status code 什麼都證明不了 ——
腳本會 sniff `<!DOCTYPE html`，並對照宣告的 content type 驗 `%PDF-`。

簽名檔案 URL 本身就是憑證。腳本不會記錄它們，也請不要把它貼到任何地方。

---

## 很多課程 PDF 沒有文字層

某一門課的 10 個檔案裡，**9 個文字層長度為 0** —— 它們是點陣掃描檔或向量圖。
這不是資料遺失。約 160 dpi 渲染成圖片再讀：

```python
import pymupdf
d = pymupdf.open("worksheet.pdf")
d[0].get_pixmap(dpi=160).save("page1.png")   # 然後讀這張圖
```

**不要**只用一種抽取路徑就判定一個 PDF 不能用。

---

## Ceiba

`ceiba.ntu.edu.tw` 沒有實作。在某些網路上連不上（DNS 有解析、
同時間三個 NTU 站台都在 150 ms 內回應，只有 ceiba 卡在 connect）。
這是網路可達性的問題，不是程式問題 —— 見
`references/ceiba-unreachable.md`，裡面有能分辨兩者的對照實驗。

---

## 檔案結構

```
SKILL.md                              規則書：驗證狀態、坑、工作流程
scripts/ntu_fetch.py                  整個工具
pyproject.toml                        讓 `ntu-cool` 變成可安裝指令
tests/test_ntu_fetch.py               41 個離線測試，不連網路
ACKNOWLEDGEMENTS.md                   哪些東西來自上游專案
references/upstream-findings.md       為什麼沒有直接沿用那份 2019 的程式
references/ceiba-unreachable.md       可達性對照實驗
references/testing-and-interpreters.md  venv 和系統 Python 的坑
```

`SKILL.md` 是寫給 **AI agent 在行動前閱讀**用的。人類也讀得懂，
但它的組織方式是「什麼已驗證、什麼沒有、什麼會咬你」。

---

## 倫理與範圍

唯讀。這個腳本發出的每一個請求都是 `GET`，
唯一的例外是取得 session 所需的兩次登入表單送出 ——
沒有上傳、沒有寫入、沒有刪除，沒有任何形式的新增或修改課程。
它遵守跟帳號持有者本人相同的規則：**登入後能看到的就抓，看不到的不碰。**

請只對自己的帳號使用。