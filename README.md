# Claude Study — Spoke (cá nhân)

> Workspace **cá nhân** cho học hỏi + side projects. Không thuộc cty nào.

## Cấu trúc

```
Claude Study/
├── seongon-led-vay/         # Side project: landing page bảng LED vẫy
├── lark-mcp/                # Side project: Lark Calendar → Google Calendar sync
├── _notes/                  # Ghi chú học, kiến thức tích lũy
├── _research/               # Research các topic mới
├── _drafts/                 # Bản nháp ý tưởng, MVP thử nghiệm
├── .mcp.json                # MCP: Lark (chỉ load khi mở Claude từ đây)
├── README.md
└── .gitignore
```

## Active projects

### 🪧 seongon-led-vay
- **Trạng thái:** đã có MVP, push lên Github (`namdangntd-sys/claude-code` cũ — sau khi tách spoke có thể tạo repo riêng)
- **Stack:** HTML + Tailwind CDN + Vanilla JS + Canvas
- **Tính năng:** Designer trực tiếp với bitmap font 5×7 + 3×5, 5 nấc cỡ chữ, orientation dọc/ngang
- **Next:** Polish UI, deploy lên hosting (Netlify/Vercel)

### 🗓️ lark-mcp
- **Trạng thái:** chờ approve Lark scope (read-only first, write later)
- **Stack:** Python + lark-mcp SDK
- **Mục tiêu:** One-way sync Lark Calendar → Google Calendar
- **Next:** Khi scope approved → test sync, deploy

## Workflow

### Bắt đầu session
```cmd
cd "C:\Users\stalk\OneDrive\Desktop\Claude Study"
code .
:: Mở Claude Code trong đây để có MCP Lark + memory riêng
```

### Deep work 1 project
- Vào sub-folder cụ thể: `cd seongon-led-vay && code .` (mở Window mới)
- Hoặc làm từ Claude Study root, chỉ rõ project nào

## MCP

`.mcp.json` ở folder này có **Lark MCP** — chỉ load khi mở Claude từ Claude Study.
Hub (Claude Code TL) không còn .mcp.json → không bị load Lark cho việc admin tổng.

⚠️ `.mcp.json` chứa Lark App Secret → đã `.gitignore`.

## Git strategy

- Có thể init repo riêng cho Claude Study (push `claude-study` repo)
- Hoặc giữ mỗi project con là 1 repo riêng (cleaner cho deploy)
- Lựa chọn sau, hiện tại chưa init

## Bảo mật

- `.gitignore` chặn: `.mcp.json`, `**/.env`, `.venv/`, `__pycache__/`, logs
- `lark-mcp/.env` có App Secret thật → KHÔNG commit
