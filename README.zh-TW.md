# ntu-cool-cli

一個 CLI，同時也是給 Agent 用的 skill —— 唯讀地讀取 NTU Cool 的課程公告、
課程檔案、CA handout 與繳交狀態。

可以直接在 shell 裡用，也可以裝成 skill 讓 agent 來驅動。

> English version: [README.md](README.md)

一個 CLI，四個資料來源。Cool 把一門課的東西分散在不同地方，而最直覺的那個
常常是空的：

| 你要找的 | 實際在哪 |
|---|---|
| 這門課公告了什麼 | `discussion_topics` —— 公告與其附件 |
| 課程檔案：講義、worksheet、解答、大綱 | Files tree（`folders`）|
| CA handout（當 Files tree 看起來是空的）| **作業描述**（`assignments`）|
| 依週分組的 lecture | **modules**（`modules` → `modules/{id}/items`）|
| 我的作業繳交了沒 | `/submissions/self` |

```bash
# 不用帳密 —— 先確認平台連不連得上
python3 scripts/ntu_fetch.py --probe

# 我這學期有哪些課
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
```

**唯讀。** 它只登入讀取，不會寫入、不會發文、不會留言。
要上傳作業是你自己在瀏覽器裡做的事。

---

## 為什麼不做成一個常駐服務

一個定時輪詢、推 Telegram 的 daemon，需要資料庫、ORM 跟 migration，
只為了回答一個 endpoint 的問題。在 Python 3.14 上那套堆疊會先三處失敗：

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

抓取本身就是合理的範圍：一個讀完就退出的腳本沒有任何東西需要同步。
儲存、去重、投遞都屬於執行它的那一層。

出處與授權說明在 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

---

## 安裝

當成指令用 —— 裝完 PATH 上會有 `ntu-cool-cli`。

**它沒有上架 PyPI。** 套件名 `ntu-cool-cli` 只存在於這個 repo 的
`pyproject.toml`，PyPI 上沒有任何發行版，所以 `pipx install ntu-cool-cli`
與 `uv tool install ntu-cool-cli` 都會失敗（no matching distribution）。
改用 Git 來源安裝：

```bash
# 直接從 Git 裝 —— 不需要先 clone
uv tool install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'
# 或用 pipx：
pipx install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'
```

或從本機 checkout 裝：

```bash
git clone https://github.com/Gary1020-byte/ntu-cool-cli.git
cd ntu-cool-cli
pipx install .          # 或：uv tool install .  /  python3 -m pip install --user .
ntu-cool-cli --probe
```

模組叫 `ntu_fetch`，指令叫 `ntu-cool-cli`，兩者做完全一樣的事 ——
`ntu-cool-cli --help` 跟 `python3 scripts/ntu_fetch.py --help` 輸出相同。
看你要哪個；那個 script 根本不需要安裝就能跑。

需要 Python 3.9+ 與 `requests`。驗證：

```bash
ntu-cool-cli --probe
```

### 測試

```bash
python3 -m unittest discover -s tests -v
```

52 個離線測試，不連網路、不用帳密。涵蓋 JSON 前綴處理、
不用 BeautifulSoup 的 HTML 表單解析、憑證檔權限防護，
以及最關鍵的一項 —— 藏在 `<head>` 的誘捕表單**永遠不會變成 POST 目標**。

有兩個 test class 守著那個默默漏抓檔案的 bug：一個讓 `_paged_get` 走過多頁的 Link
鏈，一個證明遞迴是從根進入，而且在 `/folders/root` 回 403 時仍能運作。

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

### 密碼可能從哪裡洩漏、實際上又從哪裡洩漏

密碼是當成表單欄位送到 ADFS 的。它「本來可能」做的事，跟實際的行為：

| 洩漏面 | 這個工具的行為 |
|---|---|
| 印在錯誤訊息裡 | 不會 —— 登入失敗只說是哪一段跳轉、HTTP status 多少，不會印出送出的值 |
| 被 `requests` 的除錯輸出倒出來 | 不會 —— 沒有 `enable_http_debugging()` 也沒有 `debuglevel`，而且有測試盯著它們不出現 |
| 留在 traceback 裡 | 不會 —— traceback 帶的是「呼叫了什麼」，不是「值是多少」；值只存在於 POST body |
| 放在别人讀得到的檔案裡 | 直接拒絕讀取 |

**真正的風險在你那一側：**

- **憑證檔的路徑。** `--cred-file ~/.ntu-creds.json` 會進 shell history，
  路徑也會出現在 process list。所以手動打指令時用環境變數比較安全；
  反而是 cron 這種無人值守的場景才需要檔案。
- **簽章的下載網址。** 檔案的 `url` 本身就是憑證。工具不會印它，
  也不會把它寫進任何產出的檔案。**不要貼到 issue 裡。**
- **session cookie。** 存在 `requests.Session` 裡，行程結束就消失，磁碟上不留任何東西。

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
20 則公告正文    2,041 字元   0 個檔案連結
課程 Files 樹    91 個檔案
公告附件          5 個檔案    <- 第三組
```

一則正文全文只有「attached」兩個字的公告，**不是**要回報「附件抓不到」的情況 ——
那是正常形狀，而且檔案完全抓得到。只讀公告就回報「這門課沒有附件」，
聽起來像個完整答案，實際上漏掉每一份習題。

### 坑三：從根進入、跟著 `Link` —— 三個不同的陷阱

```
GET /api/v1/courses/{id}/folders/root   → 根資料夾              <- 從這裡進
folder["files_url"]                     → 該資料夾裡的檔案       (有分頁)
folder["folders_url"]                   → 子資料夾；遞迴         (有分頁)
```

**(a) URL 要從物件的欄位讀。** 猜了六個看起來很合理的路徑，全部 404 或 400 ——
包括 `/api/v1/courses/{id}/files`，那個看起來最對，而且是死的。

**(b) `/folders` 是平清單，不是樹。** 它列出**所有深度**的資料夾。
迭代它**又**遞迴 `folders_url`，每個非根資料夾就會被走兩次 ——
若它的父資料夾也在清單裡，是三次。直覺的寫法報出**110 個檔案，實際只取得到 64 個**。
改成只從根進入。

**(c) 每個 list endpoint 預設分頁 10。** 這個才是真正丟資料的陷阱：
一個裝 29 個檔案的資料夾只回傳 10 個，沒有錯誤、沒有看起來空的尾巴。
一學期實測 —— **91 個檔案裡默默少掉 27 個**。

```
Link header 顯示:  <...>; rel="next", <...>; rel="last"
裸請求:            page=1&per_page=10
```

**跟著 `Link: rel="next"`。** 不要用「調大 per_page」來修 ——
API 會把那個參數封頂，而 Link header 是它唯一遵守的分頁契約。

`fetch_course_files()` 從 `/folders/root` 進入（`/folders` 裡 `parent_folder_id`
為 null 的那幾個作為備援，因為 `/folders/root` 在至少一門非學分課上回 **403**），
兩個方向都跟分頁，最後依 file `id` 去重當最後防線。
有測試會在三者任何一個被移除時失敗。

公告附件是**第三組**，和前兩者都不同：某學期有 5 個，Files 樹有 91 個。
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

### 作業、繳交、課程頁面、modules

```bash
# 作業清單：名稱、due_at、lock_at、配分
python3 scripts/ntu_fetch.py --list-assignments --course <COURSE> --cred-file ~/.ntu-creds.json

# 每份作業我自己的繳交狀態（唯讀）
python3 scripts/ntu_fetch.py --list-submissions --course <COURSE> --cred-file ~/.ntu-creds.json

# 課程頁面：大綱、行事曆、遲交政策、繳交方式
python3 scripts/ntu_fetch.py --list-pages --course <COURSE> --cred-file ~/.ntu-creds.json

# modules —— 依週分組的 lecture
python3 scripts/ntu_fetch.py --list-modules --course <COURSE> --cred-file ~/.ntu-creds.json

# 作業描述裡的 handout 連結（不在 Files 樹裡的那些）
python3 scripts/ntu_fetch.py --list-handouts --course <COURSE> --cred-file ~/.ntu-creds.json

# 單一課程頁面的內容，用 slug 指定（slug 列表見 --list-pages）
python3 scripts/ntu_fetch.py --show-page ke-cheng-da-gang --course <COURSE> \
    --cred-file ~/.ntu-creds.json

# 把 handout 本身下載下來
python3 scripts/ntu_fetch.py --download-handout --course <COURSE> \
    --cred-file ~/.ntu-creds.json --files-out ./handouts/
```

`lock_at` 才是真正的截止時間；`due_at` 是公告的時間，兩者之間的落差是
課程頁面承諾的寬限期。`lock_at` 已經過期 = 上傳視窗關閉了。

`--show-page` 需要剛好一門課 —— 它會印出頁面標題、網址跟純文字內容。
`--download-handout` 走兩段式下載（endpoint 回的是描述檔案的 JSON，
signed URL 在裡面），檔案會用真實檔名存檔。

---

## 當成 Agent skill 安裝

把下面這段貼給你的 agent（Claude Code、Hermes、自訂助理 —— 任何能跑指令、
讀檔案的都算）。

**Agent 必須先問你需要哪些功能，然後只裝那些。** 每個功能都對應到一個
特定 flag 或 `SKILL.md` 的一節，所以「只裝一部分」是正常情況，不是妥協。

````text
安裝 NTU Cool skill：https://github.com/Gary1020-byte/ntu-cool-cli

安裝前先問我需要哪些功能。不要全部預設安裝。功能清單：

  1. 課程公告        —— 公告、截止日、助教通知
                        flag: --course / --all-courses
  2. 課程檔案        —— Files 樹：講義、worksheet、解答、大綱 PDF
                        flags: --list-files、--download-files
  3. 公告附件        —— 綁在某一篇公告上的檔案（跟 Files 樹是不同的集合）
                        已包含在 --list-files / --download-files
  4. 作業清單        —— /assignments：有哪些作業、due_at、lock_at、
                        配分，以及 handout 連結
                        flag: --list-assignments
  5. 繳交狀態        —— 我每份作業的狀態：未繳 / 已繳 / 已批改、分數、
                        遲交狀態
                        flag: --list-submissions
  6. 課程頁面        —— 大綱、行事曆、遲交政策、繳交方式
                        flag: --list-pages
  7. Modules        —— 依週分組的 lecture
                        flag: --list-modules
  8. CA handout     —— 作業描述裡的 handout 連結，不在 Files 樹裡
                        （CA 課的 Files 樹常常近乎空白）
                        flags: --list-handouts、--download-handout
  9. 頁面內容        —— 單一課程頁面的正文：大綱、行事曆、遲交政策、
                        繳交方式
                        flag: --show-page <slug>

把這份清單列給我，問我要哪些，然後等我的回答。

接著：
  - clone 這個 repo
  - 安裝 `ntu-cool-cli` 套件。它**沒有上架 PyPI** —— 請用 Git 來源安裝：
    `uv tool install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'`
    （或 `pipx install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'`、
    或在 clone 內執行 `pipx install .`）。`pipx install ntu-cool-cli` 會失敗 ——
    PyPI 上沒有這個發行版。
  - 讀 SKILL.md，只保留我選的那些功能對應的章節
  - 告訴我怎麼提供憑證。優先用環境變數 NTU_USER 與 NTU_PASS —— 不落地、
    也不會留在 shell history。另一種是一個有 ntu_user / ntu_pass 的 JSON
    檔，用 --cred-file 帶進來；那個檔案必須是 mode 600，因為工具拒絕讀取
    其他人可讀的檔案。絕對不要把憑證寫進 repo，也絕對不要把憑證回報給我。
  - 先跑 `ntu-cool-cli --probe`。它不需要憑證，可以告訴你平台連不連得上。
    probe 沒乾淨之前不要去查憑證問題。

這工具是唯讀的。它只登入讀取，不會寫入、不會發文、不會留言。
它無法上傳作業 —— 如果我要交東西，請告訴我什麼時候要交、檔案在哪，
讓我自己用瀏覽器上傳。絕對不要嘗試對平台做任何寫入。
````

### 為什麼要 agent 先問

Cool 把一門課的東西放在四個不同地方，而哪裡放什麼從外面猜不到 ——
CA 課的 Files 樹常常近乎空白，從裡面找不到的 handout 通常在作業描述裡。
把九個功能全裝上去，會讓 agent 讀一份它根本不會查的 skill 檔，
而每一個用不上的功能都是「用錯來源回答」的機會。

這份清單同時也是一張地圖：知道「這門課的 Files 樹是空的」的 agent，
就會去問 `--list-handouts`，而不是回報「沒有附件」。

---

## 這些輸出該信多少

| 說法 | 狀態 |
|---|---|
| NTU Cool 的 endpoint 還在 | 已驗證 —— 回 401 + 有結構的 body，不是 404 |
| SAML 登入流程正確 | 已對線上站台驗證過 |
| `/api/v1/courses` 是本學期課表 | **假的** —— 見坑一 |
| Files 樹的 endpoint 形狀 | 已驗證，一學期列舉出 91 個檔案 |
| 沒有默默漏抓 | 已驗證 —— 分頁靠 `Link` 一路跟到底 |
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
pyproject.toml                        讓 `ntu-cool-cli` 變成可安裝指令
tests/test_ntu_fetch.py               52 個離線測試，不連網路
ACKNOWLEDGEMENTS.md                   哪些東西來自上游專案
references/api-findings.md            平台實際回傳什麼
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