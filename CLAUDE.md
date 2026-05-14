# Claude Study — Spoke workspace

Đây là workspace **học hỏi + side projects cá nhân** của Nam. Khác 3 spoke công ty: nơi đây Nam thử nghiệm tự do, không phải môi trường doanh nghiệp.

## Vai trò

- Học Claude Code features, Anthropic SDK, MCP server building
- Side projects: `seongon-led-vay`, `lark-mcp`
- Sandbox cho thử nghiệm tool / prompt / workflow trước khi áp dụng vào spoke công ty

## Rules riêng

- **Thoải mái experiment** — em có thể đề xuất giải pháp táo bạo hơn, refactor không cần dè dặt như môi trường cty.
- **Lỗi OK** — không có khách hàng / production traffic ảnh hưởng nếu em làm hỏng một POC.
- **Không lưu thông tin cty** ở đây — Claude Study là cá nhân.
- Code/POC ở đây có thể migrate sang spoke cty khi mature, em sẽ nhắc anh.

## File quan trọng

- `seongon-led-vay/` — side project (chưa biết chi tiết, em đọc khi mở)
- `lark-mcp/` — Lark MCP integration (xem note bảo mật bên dưới)
- `.mcp.json` — config MCP cho spoke này
- `_drafts/`, `_notes/`, `_research/`, `README.md`

## ⚠ Bảo mật Lark

File `.mcp.json` hiện tại có **app_id + app_secret hardcoded plain text**. Cần migrate sang env vars + thêm `.gitignore`. Đây là TODO em sẽ làm sau.

## Khi anh học Claude Code feature mới

- Em prefer chạy thử ngay ở đây thay vì giải thích lý thuyết
- Lưu insight có giá trị thành memory type `reference` (vd `[[claude-connectors-team-vs-personal]]`)

## Tool ưu tiên

- `lark` MCP — gắn với Lark workspace của Nam
- `WebSearch` / `WebFetch` cho tra cứu docs Claude / Anthropic
- `nam:save_memory` để ghi lại insight khi học

## Đừng làm

- Đẩy code POC lên git public mà không strip secrets
- Lấy data thật từ spoke cty làm test case cho POC ở đây
