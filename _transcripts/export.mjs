#!/usr/bin/env node
// Export Claude Code conversation transcript → Markdown.
// Usage: node _transcripts/export.mjs [outDir]
//
// Tự động tìm file .jsonl mới nhất của project hiện tại trong
// ~/.claude/projects/<encoded-cwd>/ rồi chuyển sang Markdown đẹp,
// lưu vào outDir (mặc định: _transcripts/) ngay trong workspace.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const cwd = process.cwd();
const outDir = path.resolve(process.argv[2] || path.join(cwd, '_transcripts'));

// Encode cwd theo cách Claude Code lưu project dir:
// Replace `:`, `\`, `/`, ` ` → `-`
function encodeCwd(p) {
  return p.replace(/[\\/: ]/g, '-');
}

const projectsRoot = path.join(os.homedir(), '.claude', 'projects');
const projectDir = path.join(projectsRoot, encodeCwd(cwd));

if (!fs.existsSync(projectDir)) {
  console.error(`Không tìm thấy thư mục transcript: ${projectDir}`);
  console.error(`Đảm bảo cwd hiện tại đúng là project đang chạy Claude Code.`);
  process.exit(1);
}

const jsonlFiles = fs.readdirSync(projectDir)
  .filter(f => f.endsWith('.jsonl'))
  .map(f => {
    const full = path.join(projectDir, f);
    return { name: f, full, mtime: fs.statSync(full).mtime };
  })
  .sort((a, b) => b.mtime - a.mtime);

if (jsonlFiles.length === 0) {
  console.error(`Không có file .jsonl nào trong ${projectDir}`);
  process.exit(1);
}

const latest = jsonlFiles[0];
const lines = fs.readFileSync(latest.full, 'utf8').split('\n').filter(Boolean);

const messages = [];
for (const line of lines) {
  try {
    const obj = JSON.parse(line);
    if (obj.type === 'user' || obj.type === 'assistant') messages.push(obj);
  } catch { /* skip malformed */ }
}

function fmtTextBlock(block) {
  if (typeof block === 'string') return block;
  if (block.type === 'text') return block.text || '';
  if (block.type === 'tool_use') {
    const inputStr = JSON.stringify(block.input ?? {}, null, 2);
    return `\n<details><summary>🔧 Tool: <code>${block.name}</code></summary>\n\n\`\`\`json\n${inputStr}\n\`\`\`\n\n</details>\n`;
  }
  if (block.type === 'tool_result') {
    let content = block.content;
    if (Array.isArray(content)) content = content.map(c => c.text || JSON.stringify(c)).join('\n');
    else if (typeof content !== 'string') content = JSON.stringify(content);
    const trimmed = content.length > 2000 ? content.slice(0, 2000) + '\n...(truncated)' : content;
    return `\n<details><summary>📤 Tool result${block.is_error ? ' (error)' : ''}</summary>\n\n\`\`\`\n${trimmed}\n\`\`\`\n\n</details>\n`;
  }
  if (block.type === 'thinking') return ''; // bỏ qua extended thinking
  if (block.type === 'image') return '\n*[Image attached]*\n';
  return '';
}

function fmtContent(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(fmtTextBlock).filter(Boolean).join('\n');
  return JSON.stringify(content);
}

const startTs = messages[0]?.timestamp || latest.mtime.toISOString();
const endTs = messages[messages.length - 1]?.timestamp || latest.mtime.toISOString();

let md = `# Conversation Export\n\n`;
md += `- **Session:** \`${latest.name.replace('.jsonl', '')}\`\n`;
md += `- **Project:** ${cwd}\n`;
md += `- **Bắt đầu:** ${startTs}\n`;
md += `- **Kết thúc:** ${endTs}\n`;
md += `- **Số tin nhắn:** ${messages.length}\n`;
md += `- **Xuất lúc:** ${new Date().toISOString()}\n\n`;
md += `---\n\n`;

for (const m of messages) {
  const role = m.type === 'user' ? '👤 **User**' : '🤖 **Claude**';
  const ts = m.timestamp ? ` · *${m.timestamp}*` : '';
  md += `### ${role}${ts}\n\n`;
  md += fmtContent(m.message?.content) + '\n\n';
}

fs.mkdirSync(outDir, { recursive: true });

const tsSafe = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const outFile = path.join(outDir, `conversation-${tsSafe}.md`);
fs.writeFileSync(outFile, md, 'utf8');

console.log(`✅ Đã xuất ${messages.length} tin nhắn → ${outFile}`);
console.log(`   Source: ${latest.full}`);
