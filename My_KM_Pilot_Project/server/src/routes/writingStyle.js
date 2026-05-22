import db from '../database.js';
import { v4 as uuidv4 } from 'uuid';

export default async function writingStyleRoutes(fastify, options) {

  // 1. POST /geekseek/aiwriter/writingStyle/v1/pageList
  fastify.post('/geekseek/aiwriter/writingStyle/v1/pageList', async (request, reply) => {
    const { page = 1, pageSize = 24, searchKeyword = '' } = request.body || {};
    const offset = (page - 1) * pageSize;

    let sql = `SELECT * FROM writing_styles WHERE 1=1`;
    const params = [];

    if (searchKeyword) {
      sql += ` AND title LIKE ?`;
      params.push(`%${searchKeyword}%`);
    }

    sql += ` ORDER BY created_at DESC LIMIT ? OFFSET ?`;
    params.push(pageSize, offset);

    const rows = db.prepare(sql).all(...params);

    let countSql = `SELECT COUNT(*) as total FROM writing_styles WHERE 1=1`;
    const countParams = [];
    if (searchKeyword) {
      countSql += ` AND title LIKE ?`;
      countParams.push(`%${searchKeyword}%`);
    }
    const { total } = db.prepare(countSql).get(...countParams);

    const list = rows.map(r => ({
      id: r.id,
      title: r.title,
      status: r.status,
      progress: r.progress,
      materialIds: r.material_ids ? JSON.parse(r.material_ids) : [],
      wordCloud: r.word_cloud ? JSON.parse(r.word_cloud) : [],
      materialCount: r.material_count,
      createdAt: r.created_at,
      updatedAt: r.updated_at
    }));

    return {
      code: 200,
      message: 'success',
      data: {
        list,
        total,
        page,
        pageSize
      }
    };
  });

  // 2. GET /geekseek/aiwriter/writingStyle/v1/detail
  fastify.get('/geekseek/aiwriter/writingStyle/v1/detail', async (request, reply) => {
    const { styleId } = request.query;
    if (!styleId) return reply.code(400).send({ code: 400, message: 'styleId is required' });

    const r = db.prepare(`SELECT * FROM writing_styles WHERE id = ?`).get(styleId);
    if (!r) return reply.code(404).send({ code: 404, message: 'Style not found' });

    return {
      code: 200,
      message: 'success',
      data: {
        id: r.id,
        title: r.title,
        status: r.status,
        progress: r.progress,
        materialIds: r.material_ids ? JSON.parse(r.material_ids) : [],
        wordCloud: r.word_cloud ? JSON.parse(r.word_cloud) : [],
        stylePrompt: r.style_prompt,
        materialCount: r.material_count,
        createdAt: r.created_at,
        updatedAt: r.updated_at
      }
    };
  });

  // 3. POST /geekseek/aiwriter/writingStyle/v1/query
  fastify.post('/geekseek/aiwriter/writingStyle/v1/query', async (request, reply) => {
    const { id } = request.body || {};
    if (!id) return reply.code(400).send({ code: 400, message: 'id is required' });

    const r = db.prepare(`SELECT * FROM writing_styles WHERE id = ?`).get(id);
    if (!r) return reply.code(404).send({ code: 404, message: 'Style not found' });

    // Simulate training progress incrementing by 20% on each query if not completed
    let newProgress = r.progress;
    let newStatus = r.status;
    if (r.status === 'TRAINING' && r.progress < 100) {
      newProgress = Math.min(100, r.progress + 25);
      if (newProgress === 100) {
        newStatus = 'READY';
      }
      db.prepare(`UPDATE writing_styles SET progress = ?, status = ? WHERE id = ?`)
        .run(newProgress, newStatus, id);
    }

    return {
      code: 200,
      message: 'success',
      data: {
        id: r.id,
        status: newStatus,
        progress: newProgress
      }
    };
  });

  // 4. POST /geekseek/aiwriter/writingStyle/v1/add
  fastify.post('/geekseek/aiwriter/writingStyle/v1/add', async (request, reply) => {
    const { title, materialIds = [] } = request.body || {};
    if (!title) return reply.code(400).send({ code: 400, message: 'title is required' });

    const newId = uuidv4();
    const now = new Date().toISOString();

    // Mock highly tailored official word clouds based on title or defaults
    const mockWordCloud = [
      { word: '协同办公', weight: 85 },
      { word: '数字政务', weight: 82 },
      { word: '信息流转', weight: 75 },
      { word: '统筹规划', weight: 70 },
      { word: '求真务实', weight: 65 },
      { word: '砥砺前行', weight: 62 },
      { word: '贯彻落实', weight: 58 },
      { word: '高效协同', weight: 55 },
      { word: '安全保障', weight: 50 },
      { word: '数据壁垒', weight: 48 },
      { word: '精简效能', weight: 45 }
    ];

    const stylePrompt = `【文风特质分析】：行文庄重典雅、结构高度对称、惯用“一是、二是、三是”作主轴承托，强调安全可控与协调推进。`;

    db.prepare(`
      INSERT INTO writing_styles (id, title, status, progress, material_ids, word_cloud, style_prompt, material_count, created_at, updated_at)
      VALUES (?, ?, 'TRAINING', 0, ?, ?, ?, ?, ?, ?)
    `).run(
      newId,
      title,
      JSON.stringify(materialIds),
      JSON.stringify(mockWordCloud),
      stylePrompt,
      materialIds.length,
      now,
      now
    );

    return {
      code: 200,
      message: 'success',
      data: {
        id: newId,
        title,
        status: 'TRAINING',
        progress: 0
      }
    };
  });

  // 5. POST /geekseek/aiwriter/writingStyle/v1/update
  fastify.post('/geekseek/aiwriter/writingStyle/v1/update', async (request, reply) => {
    const { id, title, materialIds = [] } = request.body || {};
    if (!id) return reply.code(400).send({ code: 400, message: 'id is required' });

    const existing = db.prepare(`SELECT * FROM writing_styles WHERE id = ?`).get(id);
    if (!existing) return reply.code(404).send({ code: 404, message: 'Style template not found' });

    const now = new Date().toISOString();

    // If materials modified, re-trigger training simulation
    const materialsChanged = JSON.stringify(materialIds) !== existing.material_ids;
    const status = materialsChanged ? 'TRAINING' : existing.status;
    const progress = materialsChanged ? 0 : existing.progress;

    db.prepare(`
      UPDATE writing_styles
      SET title = ?, material_ids = ?, material_count = ?, status = ?, progress = ?, updated_at = ?
      WHERE id = ?
    `).run(title || existing.title, JSON.stringify(materialIds), materialIds.length, status, progress, now, id);

    return {
      code: 200,
      message: 'success',
      data: {
        id,
        title: title || existing.title,
        status,
        progress
      }
    };
  });

  // 6. POST /geekseek/aiwriter/writingStyle/v1/delete
  fastify.post('/geekseek/aiwriter/writingStyle/v1/delete', async (request, reply) => {
    const { id } = request.body || {};
    if (!id) return reply.code(400).send({ code: 400, message: 'id is required' });

    db.prepare(`DELETE FROM writing_styles WHERE id = ?`).run(id);

    return { code: 200, message: 'success', data: true };
  });

  // 7. POST /geekseek/aiwriter/writingStyle/v1/downList
  fastify.post('/geekseek/aiwriter/writingStyle/v1/downList', async (request, reply) => {
    const rows = db.prepare(`SELECT id, title FROM writing_styles WHERE status = 'READY'`).all();

    const dropdown = rows.map(r => ({
      value: r.id,
      label: r.title
    }));

    // Insert a default standard official writing style
    dropdown.unshift({ value: 'default_style', label: '通用机关公文风' });

    return {
      code: 200,
      message: 'success',
      data: dropdown
    };
  });
}
