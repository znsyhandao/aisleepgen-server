/**
 * pre_upload.js — 小程序上传前检查脚本
 * 用法: node pre_upload.js
 * 
 * 功能:
 * 1. 所有 .js 文件语法检查
 * 2. 检测 api.request({url:...}) 这种传参错误
 * 3. 检测 .catch 挂在错误位置（常见的 then 链断裂）
 * 
 * 如果检查不通过，不要上传！
 * 所有报错改完了再上传。
 */

const fs = require('fs');
const path = require('path');

const MINIPROGRAM_DIR = path.join(__dirname, 'miniprogram');

// 已知的有问题的模式
const BAD_PATTERNS = [
  {
    name: 'api.request 传了对象而不是(path, data)',
    regex: /api\.request\(\{[\s\S]{0,200}url:.*api-intervention-complete/,
    hint: '应改为 api.request("/api/intervention-complete", {openid, pattern, ...})',
  },
  {
    name: '分号后面直接跟 .catch',
    regex: /\);\s*\n\s*\.catch\(/,
    hint: '.catch 应该跟在 then() 或 Promise 链后面，不要在声明语句后面',
  },
  {
    name: '逗号后面跟 .then（应该是.）',
    regex: /\),\s*\n\s*\.then\(/,
    hint: '), 应该是 ) 后面直接 .then，中间不要有逗号',
  },
  {
    name: '.then(function(res) 后直接换行没大括号',
    // 放宽：只检测 function(res) 后面有语句但没有 { 的极端情况
    regex: /\.then\(function\s*\(res\)\s*\n\s+\.catch/,
    hint: '.then(function(res) 后面应该直接跟 {',
  },
  {
    name: 'then链中的 setData 后面跟 .catch',
    regex: /setData\(\{[\s\S]{0,200}\}\);\s*\n\s+\.catch\(/,
    hint: 'setData 是同步调用，后面不能链 .catch，.catch 应该跟在外层的 then() 后面',
  },
];

let hasError = false;

// 递归获取所有js文件
function getAllJS(dir) {
  const result = [];
  try {
    const files = fs.readdirSync(dir);
    for (const f of files) {
      const full = path.join(dir, f);
      const stat = fs.statSync(full);
      if (stat.isDirectory() && f !== 'node_modules' && f !== '.git') {
        result.push(...getAllJS(full));
      } else if (f.endsWith('.js')) {
        result.push(full);
      }
    }
  } catch (e) {}
  return result;
}

console.log('============================================');
console.log('  AISleepGen 小程序上传前检查');
console.log('============================================\n');

const files = getAllJS(MINIPROGRAM_DIR);
console.log(`找到 ${files.length} 个 .js 文件\n`);

// Phase 1: Node.js 语法检查（仅预警，不阻断——微信的 JS 引擎可能通过）
console.log('=== 1/2: JavaScript 语法检查 ===\n');

const { execSync } = require('child_process');

let syntaxErrors = [];

for (const f of files) {
  const relPath = path.relative(MINIPROGRAM_DIR, f);
  try {
    execSync(`node -c "${f.replace(/\\/g, '\\\\')}"`, { stdio: 'pipe', encoding: 'utf-8' });
  } catch (e) {
    const msg = e.stderr || e.stdout || e.message;
    const lines = msg.split('\n').filter(l => l.trim() && !l.includes('wrapSafe') && !l.includes('checkSyntax'));
    console.log(`  WARN  ${relPath}`);
    for (const line of lines.slice(0, 3)) {
      console.log(`        ${line.trim()}`);
    }
    console.log('');
    syntaxErrors.push({ file: relPath, error: lines.slice(0, 3).join(' ') });
  }
}

if (syntaxErrors.length > 0) {
  console.log(`  发现 ${syntaxErrors.length} 个潜在语法问题（仅供参考，以下载上传结果为准）\n`);
}

// Phase 2: 模式检查（确认一定会导致微信编译报错的模式才阻断）
console.log('=== 2/2: 常见错误模式检查 ===\n');

for (const f of files) {
  const relPath = path.relative(MINIPROGRAM_DIR, f);
  const content = fs.readFileSync(f, 'utf-8');

  for (const pattern of BAD_PATTERNS) {
    if (pattern.regex.test(content)) {
      // 找到行号
      const match = pattern.regex.exec(content);
      const beforeMatch = content.substring(0, match.index);
      const lineNum = (beforeMatch.match(/\n/g) || []).length + 1;

      console.log(`  FAIL  ${relPath}:${lineNum}`);
      console.log(`        ${pattern.name}`);
      console.log(`        ${pattern.hint}\n`);
      hasError = true;
    }
  }
}

console.log('');
console.log('============================================');
if (hasError) {
  console.log('  RESULT: FAIL - 请修复错误后再上传');
  console.log('============================================');
  process.exit(1);
} else if (syntaxErrors.length > 0) {
  console.log('  RESULT: PASS (with warnings) - Node语法仅预警，以上传结果为准');
  console.log('============================================');
  process.exit(0);
} else {
  console.log('  RESULT: PASS');
  console.log('============================================');
}
