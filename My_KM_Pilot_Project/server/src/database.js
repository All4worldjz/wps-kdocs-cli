import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbPath = path.join(__dirname, '..', 'gai_clone_db.json');

// Helper to load data
function loadData() {
  if (!fs.existsSync(dbPath)) {
    return {
      documents: [],
      folders: [],
      materials: [],
      writing_styles: [],
      smart_layouts: [],
      async_tasks: []
    };
  }
  try {
    const raw = fs.readFileSync(dbPath, 'utf8');
    return JSON.parse(raw);
  } catch (e) {
    console.error('Error parsing JSON DB, resetting:', e);
    return {
      documents: [],
      folders: [],
      materials: [],
      writing_styles: [],
      smart_layouts: [],
      async_tasks: []
    };
  }
}

// Helper to save data
function saveData(data) {
  fs.writeFileSync(dbPath, JSON.stringify(data, null, 2), 'utf8');
}

class Statement {
  constructor(sql) {
    this.sql = sql;
    this.parse();
  }

  parse() {
    const sql = this.sql.trim();

    // Find table name
    const tableMatch = sql.match(/(?:FROM|INTO|UPDATE|DELETE\s+FROM)\s+([a-zA-Z0-9_]+)/i);
    this.table = tableMatch ? tableMatch[1].toLowerCase() : null;

    this.isSelect = /^\s*SELECT/i.test(sql);
    this.isInsert = /^\s*INSERT/i.test(sql);
    this.isUpdate = /^\s*UPDATE/i.test(sql);
    this.isDelete = /^\s*DELETE/i.test(sql);

    this.isCount = /SELECT\s+COUNT\s*\(/i.test(sql);

    // Columns for SELECT
    this.isSelectAll = /SELECT\s+\*\s+FROM/i.test(sql);
    this.selectCols = null;
    if (this.isSelect && !this.isSelectAll && !this.isCount) {
      const match = sql.match(/SELECT\s+(.+?)\s+FROM/i);
      if (match) {
        this.selectCols = match[1].split(',').map(c => c.trim().replace(/['"`]/g, ''));
      }
    }

    let paramIdx = 0;

    // Columns for INSERT
    if (this.isInsert) {
      const colMatch = sql.match(/INSERT\s+INTO\s+[a-zA-Z0-9_]+\s*\(([^)]+)\)/i);
      if (colMatch) {
        this.insertCols = colMatch[1].split(',').map(c => c.trim().replace(/['"`]/g, ''));
      }
    }

    // Set clauses for UPDATE
    if (this.isUpdate) {
      const setMatch = sql.match(/UPDATE\s+[a-zA-Z0-9_]+\s+SET\s+(.+?)(?:\s+WHERE|$)/i);
      if (setMatch) {
        const setParts = setMatch[1].split(',').map(s => s.trim());
        this.setters = [];
        setParts.forEach(set => {
          let m1 = set.match(/^([a-zA-Z0-9_]+)\s*=\s*\?$/i);
          if (m1) {
            const col = m1[1];
            const curIdx = paramIdx++;
            this.setters.push((row, args) => {
              row[col] = args[curIdx];
            });
            return;
          }
          let m2 = set.match(/^([a-zA-Z0-9_]+)\s*=\s*NULL$/i);
          if (m2) {
            const col = m2[1];
            this.setters.push((row) => {
              row[col] = null;
            });
            return;
          }
          let m3 = set.match(/^([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_]+)\s*\+\s*(\d+)$/i);
          if (m3) {
            const col = m3[1];
            const increment = parseInt(m3[3], 10);
            this.setters.push((row) => {
              row[col] = (row[col] || 0) + increment;
            });
            return;
          }
          let m4 = set.match(/^([a-zA-Z0-9_]+)\s*=\s*(.+)$/i);
          if (m4) {
            const col = m4[1];
            const valExpr = m4[2].trim().replace(/['"]/g, '');
            if (valExpr === '1') {
              this.setters.push((row) => { row[col] = 1; });
            } else if (valExpr === '0') {
              this.setters.push((row) => { row[col] = 0; });
            } else {
              this.setters.push((row) => { row[col] = valExpr; });
            }
          }
        });
      }
    }

    // WHERE clause
    const whereMatch = sql.match(/WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|$)/i);
    if (whereMatch) {
      const wherePart = whereMatch[1].trim();
      // Split by AND, but respect parens (e.g. (title LIKE ? OR content_text LIKE ?))
      const conds = [];
      let currentCond = '';
      let parenCount = 0;
      for (let i = 0; i < wherePart.length; i++) {
        const char = wherePart[i];
        if (char === '(') parenCount++;
        if (char === ')') parenCount--;

        if (parenCount === 0 && wherePart.slice(i, i + 5).toUpperCase() === ' AND ') {
          conds.push(currentCond.trim());
          currentCond = '';
          i += 4; // skip " AND"
        } else {
          currentCond += char;
        }
      }
      if (currentCond.trim()) {
        conds.push(currentCond.trim());
      }

      let whereParamIdx = paramIdx;
      const getParam = () => {
        const curIdx = whereParamIdx++;
        return (args) => args[curIdx];
      };

      this.matchers = conds.map(c => this.buildConditionMatcher(c, getParam));
      paramIdx = whereParamIdx;
    } else {
      this.matchers = [];
    }

    // ORDER BY clause
    const orderByMatch = sql.match(/ORDER\s+BY\s+(.+?)(?:\s+LIMIT|$)/i);
    if (orderByMatch) {
      const parts = orderByMatch[1].trim().split(/\s+/);
      const col = parts[0];
      const direction = (parts[1] || 'ASC').toUpperCase();
      this.sortFn = (a, b) => {
        const valA = a[col];
        const valB = b[col];
        if (valA === undefined || valA === null) return 1;
        if (valB === undefined || valB === null) return -1;
        if (valA < valB) return direction === 'ASC' ? -1 : 1;
        if (valA > valB) return direction === 'ASC' ? 1 : -1;
        return 0;
      };
    }

    // LIMIT / OFFSET
    const limitMatch = sql.match(/LIMIT\s+([0-9\?]+)(?:\s+OFFSET\s+([0-9\?]+))?/i);
    if (limitMatch) {
      const limitStr = limitMatch[1];
      const offsetStr = limitMatch[2];

      if (limitStr === '?') {
        const curIdx = paramIdx++;
        this.getLimit = (args) => args[curIdx];
      } else {
        const val = parseInt(limitStr, 10);
        this.getLimit = () => val;
      }

      if (offsetStr) {
        if (offsetStr === '?') {
          const curIdx = paramIdx++;
          this.getOffset = (args) => args[curIdx];
        } else {
          const val = parseInt(offsetStr, 10);
          this.getOffset = () => val;
        }
      } else {
        this.getOffset = () => 0;
      }
    }
  }

  buildConditionMatcher(condStr, getParam) {
    condStr = condStr.trim();
    if (condStr === '1=1') {
      return () => true;
    }

    // Parens grouping like (title LIKE ? OR content_text LIKE ?)
    if (condStr.startsWith('(') && condStr.endsWith(')')) {
      const inner = condStr.slice(1, -1).trim();
      const orParts = [];
      let currentOr = '';
      let parenCount = 0;
      for (let i = 0; i < inner.length; i++) {
        const char = inner[i];
        if (char === '(') parenCount++;
        if (char === ')') parenCount--;

        if (parenCount === 0 && inner.slice(i, i + 4).toUpperCase() === ' OR ') {
          orParts.push(currentOr.trim());
          currentOr = '';
          i += 3;
        } else {
          currentOr += char;
        }
      }
      if (currentOr.trim()) {
        orParts.push(currentOr.trim());
      }
      const matchers = orParts.map(p => this.buildConditionMatcher(p, getParam));
      return (row, args) => matchers.some(m => m(row, args));
    }

    // LIKE condition
    let likeMatch = condStr.match(/^([a-zA-Z0-9_]+)\s+LIKE\s+\?$/i);
    if (likeMatch) {
      const col = likeMatch[1];
      const paramFn = getParam();
      return (row, args) => {
        const val = row[col];
        const search = paramFn(args);
        if (val === null || val === undefined || search === null || search === undefined) return false;
        const cleanSearch = search.toString().toLowerCase().replace(/%/g, '');
        return val.toString().toLowerCase().includes(cleanSearch);
      };
    }

    // IS NULL condition
    let nullMatch = condStr.match(/^([a-zA-Z0-9_]+)\s+IS\s+NULL$/i);
    if (nullMatch) {
      const col = nullMatch[1];
      return (row) => row[col] === null || row[col] === undefined;
    }

    // IS NOT NULL condition
    let notNullMatch = condStr.match(/^([a-zA-Z0-9_]+)\s+IS\s+NOT\s+NULL$/i);
    if (notNullMatch) {
      const col = notNullMatch[1];
      return (row) => row[col] !== null && row[col] !== undefined;
    }

    // Equality with ?
    let eqMatch = condStr.match(/^([a-zA-Z0-9_]+)\s*=\s*\?$/i);
    if (eqMatch) {
      const col = eqMatch[1];
      const paramFn = getParam();
      return (row, args) => {
        const searchVal = paramFn(args);
        if (searchVal === null || searchVal === undefined) {
          return row[col] === null || row[col] === undefined;
        }
        return row[col] === searchVal ||
               (searchVal === 1 && row[col] === true) ||
               (searchVal === 0 && row[col] === false) ||
               (row[col] === 1 && searchVal === true) ||
               (row[col] === 0 && searchVal === false);
      };
    }

    // Equality with NULL literal
    let eqNullMatch = condStr.match(/^([a-zA-Z0-9_]+)\s*=\s*NULL$/i);
    if (eqNullMatch) {
      const col = eqNullMatch[1];
      return (row) => row[col] === null || row[col] === undefined;
    }

    // Equality with constant literal
    let eqLiteralMatch = condStr.match(/^([a-zA-Z0-9_]+)\s*=\s*(.+)$/i);
    if (eqLiteralMatch) {
      const col = eqLiteralMatch[1];
      let valStr = eqLiteralMatch[2].trim().replace(/['"]/g, '');
      if (valStr === '1') {
        return (row) => row[col] === 1 || row[col] === true;
      } else if (valStr === '0') {
        return (row) => row[col] === 0 || row[col] === false;
      } else {
        return (row) => row[col] === valStr;
      }
    }

    return () => true;
  }

  all(...args) {
    const data = loadData();
    const rows = data[this.table] || [];

    if (this.isSelect) {
      let filtered = rows;
      if (this.matchers.length > 0) {
        filtered = rows.filter(row => this.matchers.every(m => m(row, args)));
      }

      if (this.isCount) {
        return [{ total: filtered.length }];
      }

      if (this.sortFn) {
        filtered = [...filtered].sort(this.sortFn);
      }

      if (this.getLimit) {
        const limit = this.getLimit(args);
        const offset = this.getOffset ? this.getOffset(args) : 0;
        filtered = filtered.slice(offset, offset + limit);
      }

      if (this.selectCols) {
        filtered = filtered.map(row => {
          const res = {};
          this.selectCols.forEach(col => {
            res[col] = row[col];
          });
          return res;
        });
      }

      return filtered;
    }

    return [];
  }

  get(...args) {
    const res = this.all(...args);
    if (this.isCount) {
      return res[0];
    }
    return res[0] || undefined;
  }

  run(...args) {
    const data = loadData();
    if (!data[this.table]) {
      data[this.table] = [];
    }

    if (this.isInsert) {
      const newRow = {};
      this.insertCols.forEach((col, idx) => {
        newRow[col] = args[idx];
      });
      data[this.table].push(newRow);
      saveData(data);
      return { changes: 1, lastInsertRowid: newRow.id || null };
    }

    if (this.isUpdate) {
      let updatedCount = 0;
      data[this.table] = data[this.table].map(row => {
        const matches = this.matchers.every(m => m(row, args));
        if (matches) {
          updatedCount++;
          const rowCopy = { ...row };
          this.setters.forEach(setter => setter(rowCopy, args));
          return rowCopy;
        }
        return row;
      });
      if (updatedCount > 0) {
        saveData(data);
      }
      return { changes: updatedCount };
    }

    if (this.isDelete) {
      const initialLength = data[this.table].length;
      data[this.table] = data[this.table].filter(row => {
        const matches = this.matchers.every(m => m(row, args));
        return !matches;
      });
      const deletedCount = initialLength - data[this.table].length;
      if (deletedCount > 0) {
        saveData(data);
      }
      return { changes: deletedCount };
    }

    return { changes: 0 };
  }
}

class MockDB {
  exec(sql) {
    const data = loadData();
    const tableMatches = sql.matchAll(/CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z0-9_]+)/gi);
    for (const m of tableMatches) {
      const t = m[1].toLowerCase();
      if (!data[t]) {
        data[t] = [];
      }
    }
    saveData(data);
    console.log('Database schema verified/created.');
  }

  pragma(sql) {
    // WAL pragma can be ignored
  }

  prepare(sql) {
    return new Statement(sql);
  }

  transaction(fn) {
    return (...args) => {
      // In-memory pure JS DB operations are synchronous and atomic by nature here,
      // so we can simply wrap it directly.
      return fn(...args);
    };
  }
}

const db = new MockDB();

// Initialize tables as specified in the schema
db.exec(`
  CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content_html TEXT NOT NULL,
    content_text TEXT NOT NULL,
    category TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    is_imported_knowledge INTEGER DEFAULT 0,
    parse_status TEXT DEFAULT 'SUCCESS',
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
  );

  CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    parent_id TEXT,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    material_type TEXT NOT NULL,
    source TEXT DEFAULT '自主上传',
    channel TEXT NOT NULL,
    folder_id TEXT,
    category TEXT DEFAULT '其他',
    content_preview TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    file_id TEXT,
    is_imported_knowledge INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    deleted_at TEXT
  );

  CREATE TABLE IF NOT EXISTS writing_styles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'READY',
    progress INTEGER DEFAULT 100,
    material_ids TEXT,
    word_cloud TEXT,
    style_prompt TEXT,
    material_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS smart_layouts (
    id TEXT PRIMARY KEY,
    source_file_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'SUCCESS',
    output_doc_id TEXT,
    word_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS async_tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    subject_id TEXT,
    status TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    input_json TEXT,
    output_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
`);

// Insert default document, material, and style if database is fresh
const data = loadData();
if (data.documents.length === 0) {
  console.log('Inserting seed data into the pure JS DB...');
  const now = new Date().toISOString();

  // Seed documents
  data.documents.push(
    {
      id: 'doc-1',
      title: '凝心聚力谋发展，砥砺奋进谱新篇',
      content_html: '<p>凝心聚力谋发展，砥砺奋进谱新篇。加快数字化转型，提升党政机关办公效能，在新的历史起点上取得更大成就。</p>',
      content_text: '凝心聚力谋发展，砥砺奋进谱新篇。加快数字化转型，提升党政机关办公效能，在新的历史起点上取得更大成就。',
      category: 'SPEECH',
      word_count: 3465,
      is_imported_knowledge: 0,
      parse_status: 'SUCCESS',
      version: 1,
      created_at: now,
      updated_at: now,
      deleted_at: null
    },
    {
      id: 'doc-2',
      title: '关于推进数字化转型工作的通知',
      content_html: '<p>各部门：为了贯彻落实数字化办公要求，现将有关推进事项通知如下：一、提高思想认识...二、明确工作重点...三、强化组织保障。</p>',
      content_text: '各部门：为了贯彻落实数字化办公要求，现将有关推进事项通知如下：一、提高思想认识...二、明确工作重点...三、强化组织保障。',
      category: 'NOTICE',
      word_count: 681,
      is_imported_knowledge: 0,
      parse_status: 'SUCCESS',
      version: 1,
      created_at: now,
      updated_at: now,
      deleted_at: null
    },
    {
      id: 'doc-3',
      title: 'gai_cn_safe_upload_test',
      content_html: '<p>公文安全上传与智能解析系统测试内容。用于验证平台对仿宋字体、公文间距以及目录排版结构的提取精准度。</p>',
      content_text: '公文安全上传与智能解析系统测试内容。用于验证平台对仿宋字体、公文间距以及目录排版结构的提取精准度。',
      category: 'FREE_WRITING',
      word_count: 155,
      is_imported_knowledge: 0,
      parse_status: 'SUCCESS',
      version: 1,
      created_at: now,
      updated_at: now,
      deleted_at: null
    },
    {
      id: 'doc-4',
      title: '通用模板-无红头',
      content_html: '<p>公文排版通用格式（无红头）。适用于各类机关企事业单位报告、请示、函等文种的快速套用和规范化输出。</p>',
      content_text: '公文排版通用格式（无红头）。适用于各类机关企事业单位报告、请示、函等文种的快速套用 and 规范化输出。',
      category: 'FREE_WRITING',
      word_count: 1414,
      is_imported_knowledge: 1,
      parse_status: 'SUCCESS',
      version: 1,
      created_at: now,
      updated_at: now,
      deleted_at: null
    }
  );

  // Seed materials
  data.materials.push({
    id: 'mat-1',
    title: 'gai_cn_safe_upload_test',
    material_type: 'PERSONAL_MATERIAL',
    source: '自主上传',
    channel: 'PERSONAL_MATERIAL',
    folder_id: null,
    category: '其他',
    content_preview: '公文安全上传与智能解析系统测试内容。用于验证平台对仿宋字体、公文间距以及目录排版结构的提取精准度。',
    word_count: 155,
    file_id: 'file-123',
    is_imported_knowledge: 0,
    created_at: now,
    deleted_at: null
  });

  // Seed writing_styles
  data.writing_styles.push({
    id: 'style-1',
    title: '测试文风模板–请删除',
    status: 'READY',
    progress: 100,
    material_ids: '["mat-1"]',
    word_cloud: JSON.stringify([
      { text: '数字化', value: 30 },
      { text: '发展', value: 25 },
      { text: '安全', value: 20 },
      { text: '公文', value: 18 },
      { text: '智能', value: 15 },
      { text: '转型', value: 12 }
    ]),
    style_prompt: '请采用一种严谨、规范、具有高度概括力的党政公文文风。多用四字词组，结构清晰，逻辑严密。',
    material_count: 1,
    created_at: now,
    updated_at: now
  });

  saveData(data);
  console.log('Seed data inserted successfully.');
}

export default db;
