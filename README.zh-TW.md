# AGY Session Manager (`agym`)

[English](README.md) | [繁體中文](README.zh-TW.md)

一款專為 **Google Antigravity CLI (`agy`)** 打造的終端互動式 Session Manager，參考 Claude Code 的操作體驗，讓你可以即時檢視所有 session 的執行狀態動畫、秒切多開背景 session、跨 session 傳訊與轉交上下文、並排監看、全文檢索歷史對話，並支援單筆與批次刪除管理。

---

## 主要特色

- **無縫快速切回 Manager**：在任何 `agy` session 視窗中於空白輸入框按 **`←`**（或任意時刻按 **`Alt+←`** / **`Ctrl+←`**）即可立即切回 Session Manager，原本的 session 會在背景持續執行不中斷。
- **即時狀態動畫與權限提醒**：直接唯讀整合 `agy` 原生的 `conversation_summaries.db`、`presence/*.lock` 與即時 tmux 畫面偵測，呈現每個 session 的狀態：
  - `⚠`（紅／黃閃爍 + `WAITING`）：正在等待使用者權限確認或輸入（置頂顯示，按 **`w`** 一鍵輪流跳轉處理）
  - `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`（青色動畫）：`RUNNING` 執行中
  - `◐◓◑◒`（黃色動畫）：背景任務 / Subagent 執行中 (`not_fully_idle`)
  - `●`（綠色）：已在背景開啟、待命中（按 `Enter` 秒切回去）
  - `◉`（紫色）：在其他終端機開啟中
  - `○`（灰色）：歷史紀錄（按 `Enter` 自動 `cd` 到原目錄並 `agy --conversation <id>` 恢復）
- **跨 Session 協作（傳訊 / 廣播 / 上下文轉交）**：
  - 按 **`m`** 可對單一或多選 sessions 傳送指令（背景執行中的視窗透過安全 bracketed paste 直接送入；歷史 session 透過背景 `agy --print=...` 執行）。
  - 按 **`c`** 可自動摘要來源 session 的最近對話與 artifacts，於可編輯視窗中確認後以 `Ctrl+S` 轉交給目標 session。
- **雙視窗並排監看 (`v`)**：多選 2 個 sessions 按 **`v`**（或單選按 **`v`** 挑選第二個 session）即可於同一 tmux 視窗左右並排檢視，支援取消並排拆回獨立視窗。
- **Fork / Subagent 樹狀檢視 (`t`)**：按 **`t`** 切換父子對話樹狀檢視（顯示 `├─` / `└─` 階層與 subagent 標籤）。
- **雙欄即時預覽與全文檢索 (`/`)**：右側面板自動解析 `transcript.jsonl` 顯示最近幾輪對話（尚未存檔或等待權限時即時擷取終端畫面），並支援標題、Workspace 路徑與 SQLite FTS5 全文檢索。
- **單刪與多選批次刪除 (`d`)**：支援 `Space` 多選、`a` 全選，透過下方確認列二次按 `d` 安全刪除（同步清理資料庫索引、`jetbox_summaries_proto.pb`、`conversations/`、`brain/`、`annotations/`、`presence/`、快取與自訂標籤）。
- **中／英雙語介面（自動偵測系統語系）**：啟動時自動依系統 `LC_ALL` / `LC_MESSAGES` / `LANG` 決定顯示語言，亦支援 `AGYM_LANG=en|zh` 指定，或在 TUI 內按 **`l`** 即時切換並記憶於 `~/.config/agy-session-manager/meta.json`。
- **獨立無干擾架構**：使用獨立 `tmux` socket (`-L agym`) 且隱藏狀態列，不干擾原本的 `tmux` 環境，並支援 Detach 保持背景續跑（SSH 斷線重連後所有 session 仍在）。

---

## 系統需求

- **Google Antigravity CLI (`agy`)** 已安裝並在 `$PATH` 中
- **tmux**（建議 `>= 3.2`）
- **Python 3.10+**（含 `venv` 模組）

---

## 快速安裝

在任意 Linux / macOS 主機上執行：

```bash
git clone https://github.com/rbtyan/agy-session-manager.git ~/.local/share/agy-session-manager
~/.local/share/agy-session-manager/install.sh
```

`install.sh` 會自動：
1. 檢查 `python3`、`tmux`、`agy`
2. 在專案目錄內建立獨立 `.venv` 並安裝 `textual`
3. 建立符號連結 `~/.local/bin/agym`

若 `~/.local/bin` 不在 `$PATH` 中，請將以下行加入 `~/.bashrc` 或 `~/.zshrc`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 更新版本

```bash
cd ~/.local/share/agy-session-manager
git pull
./install.sh
agym kill   # 若背景已有舊版 agym 執行中，重啟以載入新版
```

### 解除安裝

```bash
agym kill
rm -f ~/.local/bin/agym
rm -rf ~/.local/share/agy-session-manager
# 如需一併清除自訂名稱、釘選與語系設定：
# rm -rf ~/.config/agy-session-manager
```

---

## 使用方式

### CLI 指令

| 指令 | 說明 |
| :--- | :--- |
| `agym` | 啟動（或重新連線到）互動式 Session Manager TUI |
| `agym -l` / `--list` | 以純文字快速列出最近 25 個 sessions 與狀態 |
| `agym kill` | 關閉背景 `agym` tmux server 與所有託管的 session 視窗 |
| `agym -h` / `--help` | 顯示說明 |

### 環境變數

| 變數 | 說明 |
| :--- | :--- |
| `AGYM_LANG=en\|zh` | 覆寫自動偵測的介面語系（`en` 或 `zh`） |

### 快捷鍵一覽

#### 在 `agy` Session 視窗內
| 快捷鍵 | 功能 |
| :--- | :--- |
| **`←`**（空白輸入框） | 切回 Session Manager（輸入文字中時正常移動游標） |
| **`Alt+←`** / **`Ctrl+←`** | 無條件瞬間切回 Session Manager |

#### 在 Session Manager TUI 內
| 快捷鍵 | 功能 |
| :--- | :--- |
| **`↑` / `↓`** | 移動游標並即時預覽右側對話內容 |
| **`Enter`** | 切換到背景執行中的 session，或自動 `cd` 並恢復歷史 session |
| **`Space`** | 勾選 / 取消勾選目前 session（游標停留在原位） |
| **`a`** | 全選目前列表所有 session（再按一次全部取消） |
| **`d`** / **`Delete`** | 刪除目前游標項目（或全部已勾選項目）：下方顯示確認列，再按一次 **`d`** 確認、`Esc` 取消 |
| **`m`** | 傳送訊息或廣播指令給目前項目（或全部已勾選 sessions），於背景 worker 執行不阻塞介面 |
| **`c`** | 跨 Session 上下文轉交：自動整理來源摘要與 artifacts，可編輯後 `Ctrl+S` 轉交給目標 session |
| **`w`** | 一鍵跳轉至正在等待權限確認 (`⚠`) 的 session（多個時依序輪跳） |
| **`v`** | 雙視窗並排監看：多選 2 個直接左右並排，單選則開啟清單挑選第二個 session（已並排者可拆回獨立視窗） |
| **`t`** | 切換 Fork / Subagent 樹狀檢視模式 |
| **`n`** | 開啟新 `agy` session（可指定目錄與額外旗標如 `--mode plan`） |
| **`k`** | 關閉目前游標對應的背景執行視窗／pane（保留對話歷史紀錄） |
| **`r`** | 重新命名 session（同步寫入 AGY 的 `annotations/<id>.pbtxt` 與 `conversation_summaries.db`） |
| **`p`** | 釘選 / 取消釘選（`★` 置頂顯示） |
| **`/`** | 開啟搜尋列（支援標題、目錄與 FTS5 全文檢索），`Esc` 清除並關閉 |
| **`Tab`** | 切換「全部 Workspace / 僅當前啟動目錄」 |
| **`l`** | 即時切換介面語系（英文 / 繁體中文，並自動記憶偏好） |
| **`q`** | 離開確認列：再按 **`q`** Detach 保持背景續跑、按 **`k`** 全部關閉並離開、`Esc` 取消 |
| **`Esc`** | 依序取消確認列 → 關閉搜尋列 → 清除多選勾選 |

---

## 架構與資料安全

```text
agy-session-manager/
├── agym             # 啟動腳本（建立/連線至 tmux -L agym）
├── tmux.conf        # 獨立 tmux 設定（隱藏狀態列、滑鼠捲動、快速返回綁定）
├── double_left.sh   # 空白輸入框左鍵偵測腳本
├── tui.py           # Textual 雙欄 TUI 介面與動畫排程
├── i18n.py          # 中／英雙語系與系統語系自動偵測
├── data.py          # 唯讀 SQLite / FTS5 / presence lock / transcript / 樹狀與刪除清理
├── tmux_ctrl.py     # tmux pane/視窗管理、並排監看與權限提示偵測
├── install.sh       # 跨主機一鍵安裝腳本
└── requirements.txt # Python 套件相依（textual）
```

- **平常瀏覽皆採 SQLite 唯讀模式 (`mode=ro`)** 讀取 `~/.gemini/antigravity-cli/conversation_summaries.db`，避免鎖定衝突。
- **自訂別名、釘選與語系偏好**獨立存放在 `~/.config/agy-session-manager/meta.json`。
- **刪除操作**採用 WAL 安全的短交易（`busy_timeout = 5000`），且會先關閉對應的 `agym` 背景視窗再清理檔案。

---

## License

MIT
