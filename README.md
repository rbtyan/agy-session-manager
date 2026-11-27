# AGY Session Manager (`agym`)

一款專為 **Google Antigravity CLI (`agy`)** 打造的終端互動式 Session Manager，參考 Claude Code 的操作體驗，讓你可以即時檢視所有 session 的執行狀態動畫、秒切多開背景 session、全文檢索歷史對話，並支援單筆與批次刪除管理。

---

## 主要特色

- **無縫快速切回 Manager**：在任何 `agy` session 視窗中**快速連按兩次左鍵 (`← ←`)**（或 `Alt+←` / `Ctrl+←`）即可立即切回 Session Manager，原本的 session 會在背景持續執行不中斷。
- **即時狀態動畫**：直接唯讀整合 `agy` 原生的 `conversation_summaries.db` 與 `presence/*.lock`，即時呈現每個 session 的狀態：
  - `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`（青色動畫）：`RUNNING` 執行中
  - `◐◓◑◒`（黃色動畫）：背景任務 / Subagent 執行中 (`not_fully_idle`)
  - `●`（綠色）：已在背景開啟、待命中（按 `Enter` 秒切回去）
  - `◉`（紫色）：在其他終端機開啟中
  - `○`（灰色）：歷史紀錄（按 `Enter` 自動 `cd` 到原目錄並 `agy --conversation <id>` 恢復）
- **雙欄即時預覽**：右側面板自動解析 `transcript.jsonl` 顯示最近幾輪對話；尚未存檔的新視窗則即時擷取終端畫面預覽。
- **標題與全文檢索**：按 `/` 即可同時過濾標題、Workspace 路徑與 SQLite FTS5 對話全文內容。
- **單刪與多選批次刪除**：支援 `Space` 多選、`a` 全選，並透過下方訊息列二次按 `d` 確認後安全刪除（同步清理資料庫索引、`conversations/`、`brain/`、`annotations/`、`presence/`、快取與自訂標籤）。
- **獨立無干擾架構**：使用獨立 `tmux` socket (`-L agym`) 且隱藏狀態列，不干擾你原本的 `tmux` 環境，並支援 Detach 保持背景續跑（SSH 斷線重連後所有 session 仍在）。

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
# 如需一併清除自訂名稱與釘選設定：
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

### 快捷鍵一覽

#### 在 `agy` Session 視窗內
| 快捷鍵 | 功能 |
| :--- | :--- |
| **`← ←`**（快速雙擊） | 切回 Session Manager（間隔 `60ms ~ 350ms` 觸發；單按與長按移動游標正常透傳） |
| **`Alt+←`** / **`Ctrl+←`** | 無條件瞬間切回 Session Manager |

#### 在 Session Manager TUI 內
| 快捷鍵 | 功能 |
| :--- | :--- |
| **`↑` / `↓`** | 移動游標並即時預覽右側對話內容 |
| **`Enter`** | 切換到背景執行中的 session，或自動 `cd` 並恢復歷史 session |
| **`Space`** | 勾選 / 取消勾選目前 session（游標停留在原位） |
| **`a`** | 全選目前列表所有 session（再按一次全部取消） |
| **`d`** / **`Delete`** | 刪除目前游標項目（或全部已勾選項目）：下方顯示確認列，再按一次 **`d`** 確認、`Esc` 取消 |
| **`n`** | 開啟新 `agy` session（可指定目錄與額外旗標如 `--mode plan`） |
| **`k`** | 關閉目前游標對應的背景執行視窗（保留對話歷史紀錄） |
| **`r`** | 重新命名 session（同步寫入 AGY 的 `annotations/<id>.pbtxt` 與 `conversation_summaries.db`；若視窗已開啟，重開後標題列即同步更新） |
| **`p`** | 釘選 / 取消釘選（`★` 置頂顯示） |
| **`/`** | 開啟搜尋列（支援標題、目錄與 FTS5 全文檢索），`Esc` 清除並關閉 |
| **`Tab`** | 切換「全部 Workspace / 僅當前啟動目錄」 |
| **`q`** | 離開確認列：再按 **`q`** Detach 保持背景續跑、按 **`k`** 全部關閉並離開、`Esc` 取消 |
| **`Esc`** | 依序取消確認列 → 關閉搜尋列 → 清除多選勾選 |

---

## 架構與資料安全

```text
agy-session-manager/
├── agym             # 啟動腳本（建立/連線至 tmux -L agym）
├── tmux.conf        # 獨立 tmux 設定（隱藏狀態列、滑鼠捲動、雙擊左鍵綁定）
├── double_left.sh   # 雙擊左鍵防誤觸偵測腳本（過濾長按連發 < 60ms）
├── tui.py           # Textual 雙欄 TUI 介面與動畫排程
├── data.py          # 唯讀 SQLite / FTS5 / presence lock / transcript 解析與刪除清理
├── tmux_ctrl.py     # tmux 視窗管理與 pane 擷取控制層
├── install.sh       # 跨主機一鍵安裝腳本
└── requirements.txt # Python 套件相依（textual）
```

- **平常瀏覽皆採 SQLite 唯讀模式 (`mode=ro`)** 讀取 `~/.gemini/antigravity-cli/conversation_summaries.db`，避免鎖定衝突。
- **自訂別名與釘選狀態**獨立存放在 `~/.config/agy-session-manager/meta.json`。
- **刪除操作**採用 WAL 安全的短交易（`busy_timeout = 5000`），且會先關閉對應的 `agym` 背景視窗再清理檔案。

---

## 常見微調

### 調整雙擊左鍵 (`← ←`) 的靈敏度
編輯 [double_left.sh](double_left.sh) 中的毫秒區間（預設 `60ms` 至 `350ms`）：

```sh
if [ "$DIFF" -ge 60 ] && [ "$DIFF" -le 350 ]; then
```

---

## License

MIT
