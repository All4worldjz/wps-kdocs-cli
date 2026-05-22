import db from '../database.js';
import { v4 as uuidv4 } from 'uuid';

export default async function documentRoutes(fastify, options) {

  // 1. POST /geekseek/aiwriter/document/v1/list
  fastify.post('/geekseek/aiwriter/document/v1/list', async (request, reply) => {
    const {
      page = 1,
      pageSize = 24,
      searchKeyword = '',
      filterImportedKnowledge = false,
      isRecycled = false // Recycle bin filter
    } = request.body || {};

    const offset = (page - 1) * pageSize;
    let sql = `SELECT * FROM documents WHERE 1=1`;
    const params = [];

    if (isRecycled) {
      sql += ` AND deleted_at IS NOT NULL`;
    } else {
      sql += ` AND deleted_at IS NULL`;
    }

    if (searchKeyword) {
      sql += ` AND (title LIKE ? OR content_text LIKE ?)`;
      params.push(`%${searchKeyword}%`, `%${searchKeyword}%`);
    }

    if (filterImportedKnowledge) {
      sql += ` AND is_imported_knowledge = 1`;
    }

    sql += ` ORDER BY updated_at DESC LIMIT ? OFFSET ?`;
    params.push(pageSize, offset);

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    // Get total count
    let countSql = `SELECT COUNT(*) as total FROM documents WHERE 1=1`;
    const countParams = [];
    if (isRecycled) {
      countSql += ` AND deleted_at IS NOT NULL`;
    } else {
      countSql += ` AND deleted_at IS NULL`;
    }
    if (searchKeyword) {
      countSql += ` AND (title LIKE ? OR content_text LIKE ?)`;
      countParams.push(`%${searchKeyword}%`, `%${searchKeyword}%`);
    }
    if (filterImportedKnowledge) {
      countSql += ` AND is_imported_knowledge = 1`;
    }

    const countStmt = db.prepare(countSql);
    const { total } = countStmt.get(...countParams);

    // Map DB fields to camelCase as expected by frontend
    const documents = rows.map(r => ({
      id: r.id,
      title: r.title,
      contentHtml: r.content_html,
      contentText: r.content_text,
      category: r.category,
      wordCount: r.word_count,
      isImportedKnowledge: r.is_imported_knowledge === 1,
      parseStatus: r.parse_status,
      version: r.version,
      createdAt: r.created_at,
      updatedAt: r.updated_at,
      deletedAt: r.deleted_at
    }));

    return {
      code: 200,
      message: 'success',
      data: {
        list: documents,
        total,
        page,
        pageSize
      }
    };
  });

  // 2. GET /geekseek/aiwriter/document/v1/detail
  fastify.get('/geekseek/aiwriter/document/v1/detail', async (request, reply) => {
    const { docId, version } = request.query;

    if (!docId) {
      return reply.code(400).send({ code: 400, message: 'docId is required' });
    }

    const row = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(docId);

    if (!row) {
      return reply.code(404).send({ code: 404, message: 'Document not found' });
    }

    const doc = {
      id: row.id,
      title: row.title,
      contentHtml: row.content_html,
      contentText: row.content_text,
      category: row.category,
      wordCount: row.word_count,
      isImportedKnowledge: row.is_imported_knowledge === 1,
      parseStatus: row.parse_status,
      version: row.version,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      deletedAt: row.deleted_at
    };

    return {
      code: 200,
      message: 'success',
      data: doc
    };
  });

  // 3. POST /geekseek/aiwriter/document/v1/addOrUpdate
  fastify.post('/geekseek/aiwriter/document/v1/addOrUpdate', async (request, reply) => {
    const {
      id,
      title,
      contentHtml = '',
      contentText = '',
      category = 'FREE_WRITING',
      wordCount
    } = request.body || {};

    const now = new Date().toISOString();
    const finalWordCount = wordCount !== undefined ? wordCount : contentText.length;

    if (id) {
      // Update
      const existing = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(id);
      if (!existing) {
        return reply.code(404).send({ code: 404, message: 'Document not found' });
      }

      db.prepare(`
        UPDATE documents
        SET title = ?, content_html = ?, content_text = ?, category = ?, word_count = ?, version = version + 1, updated_at = ?
        WHERE id = ?
      `).run(title || existing.title, contentHtml, contentText, category, finalWordCount, now, id);

      const updated = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(id);
      return {
        code: 200,
        message: 'success',
        data: {
          id: updated.id,
          title: updated.title,
          version: updated.version
        }
      };
    } else {
      // Create
      const newId = uuidv4();
      const finalTitle = title || '未命名文稿';

      db.prepare(`
        INSERT INTO documents (id, title, content_html, content_text, category, word_count, is_imported_knowledge, parse_status, version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, 'SUCCESS', 1, ?, ?)
      `).run(newId, finalTitle, contentHtml, contentText, category, finalWordCount, now, now);

      return {
        code: 200,
        message: 'success',
        data: {
          id: newId,
          title: finalTitle,
          version: 1
        }
      };
    }
  });

  // 4. POST /geekseek/aiwriter/document/v1/addDocToKnowledge
  fastify.post('/geekseek/aiwriter/document/v1/addDocToKnowledge', async (request, reply) => {
    const { docId } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    db.prepare(`UPDATE documents SET is_imported_knowledge = 1, updated_at = ? WHERE id = ?`)
      .run(new Date().toISOString(), docId);

    return { code: 200, message: 'success', data: true };
  });

  // 5. POST /geekseek/aiwriter/document/v1/cancelAddDocToKnowledge
  fastify.post('/geekseek/aiwriter/document/v1/cancelAddDocToKnowledge', async (request, reply) => {
    const { docId } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    db.prepare(`UPDATE documents SET is_imported_knowledge = 0, updated_at = ? WHERE id = ?`)
      .run(new Date().toISOString(), docId);

    return { code: 200, message: 'success', data: true };
  });

  // 6. POST /geekseek/aiwriter/document/v1/recycle
  fastify.post('/geekseek/aiwriter/document/v1/recycle', async (request, reply) => {
    const { ids = [], action = 'delete' } = request.body || {}; // action: 'delete' (move to recycle) or 'restore'

    if (!ids || ids.length === 0) {
      return reply.code(400).send({ code: 400, message: 'ids are required' });
    }

    const now = action === 'delete' ? new Date().toISOString() : null;

    const stmt = db.prepare(`UPDATE documents SET deleted_at = ?, updated_at = ? WHERE id = ?`);

    // Batch run
    const transaction = db.transaction((idList) => {
      for (const id of idList) {
        stmt.run(now, new Date().toISOString(), id);
      }
    });

    transaction(ids);

    return { code: 200, message: 'success', data: true };
  });

  // 7. POST /geekseek/aiwriter/document/v1/addToPersonalMaterial
  fastify.post('/geekseek/aiwriter/document/v1/addToPersonalMaterial', async (request, reply) => {
    const { docId } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    const doc = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(docId);
    if (!doc) return reply.code(404).send({ code: 404, message: 'Document not found' });

    const matId = uuidv4();
    const now = new Date().toISOString();

    db.prepare(`
      INSERT INTO materials (id, title, material_type, source, channel, category, content_preview, word_count, file_id, is_imported_knowledge, created_at)
      VALUES (?, ?, ?, '自主上传', 'PERSONAL_MATERIAL', '其他', ?, ?, ?, ?, ?)
    `).run(matId, doc.title, 'PERSONAL_MATERIAL', doc.content_text.slice(0, 300), doc.word_count, null, doc.is_imported_knowledge, now);

    return { code: 200, message: 'success', data: { materialId: matId } };
  });

  // 8. POST /geekseek/aiwriter/document/v1/convertPunctuation
  fastify.post('/geekseek/aiwriter/document/v1/convertPunctuation', async (request, reply) => {
    const { docId } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    // In a real app this convert punctuation between standard formats. Let's return success.
    return { code: 200, message: 'success', data: true };
  });

  // 9. POST /geekseek/aiwriter/document/v1/version/list
  fastify.post('/geekseek/aiwriter/document/v1/version/list', async (request, reply) => {
    const { docId } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    const doc = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(docId);
    if (!doc) return reply.code(404).send({ code: 404, message: 'Document not found' });

    return {
      code: 200,
      message: 'success',
      data: [
        { version: doc.version, updatedAt: doc.updated_at, operator: '测试用户' }
      ]
    };
  });

  // 10. POST /geekseek/aiwriter/document/v1/categorySort
  fastify.post('/geekseek/aiwriter/document/v1/categorySort', async (request, reply) => {
    // Simply return success
    return { code: 200, message: 'success', data: true };
  });

  // 11. POST /geekseek/aiwriter/document/v1/webSearch
  fastify.post('/geekseek/aiwriter/document/v1/webSearch', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: [
        { title: '官方数字政府建设指导意见', url: 'https://gov.cn', summary: '意见强调加快数字化协同办公及智能写作辅助工具的开发与部署。' }
      ]
    };
  });
}
