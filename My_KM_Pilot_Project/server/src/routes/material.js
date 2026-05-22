import db from '../database.js';
import { v4 as uuidv4 } from 'uuid';

export default async function materialRoutes(fastify, options) {

  // 1. POST /geekseek/aiwriter/document/v2/list
  fastify.post('/geekseek/aiwriter/document/v2/list', async (request, reply) => {
    const {
      page = 1,
      pageSize = 24,
      channel = 'PERSONAL_MATERIAL', // PERSONAL_MATERIAL, QIANGGUO_ARTICLE etc
      searchKeyword = '',
      category = '', // 工作报告 | 通知 | 领导讲话 | 心得体会 etc
      folderId = null,
      filterImportedKnowledge = false
    } = request.body || {};

    const offset = (page - 1) * pageSize;
    let sql = `SELECT * FROM materials WHERE channel = ? AND deleted_at IS NULL`;
    const params = [channel];

    if (searchKeyword) {
      sql += ` AND title LIKE ?`;
      params.push(`%${searchKeyword}%`);
    }

    if (category && category !== '全部') {
      sql += ` AND category = ?`;
      params.push(category);
    }

    if (folderId) {
      if (folderId === 'root') {
        sql += ` AND folder_id IS NULL`;
      } else {
        sql += ` AND folder_id = ?`;
        params.push(folderId);
      }
    }

    if (filterImportedKnowledge) {
      sql += ` AND is_imported_knowledge = 1`;
    }

    sql += ` ORDER BY created_at DESC LIMIT ? OFFSET ?`;
    params.push(pageSize, offset);

    const rows = db.prepare(sql).all(...params);

    // Count
    let countSql = `SELECT COUNT(*) as total FROM materials WHERE channel = ? AND deleted_at IS NULL`;
    const countParams = [channel];
    if (searchKeyword) {
      countSql += ` AND title LIKE ?`;
      countParams.push(`%${searchKeyword}%`);
    }
    if (category && category !== '全部') {
      countSql += ` AND category = ?`;
      countParams.push(category);
    }
    if (folderId) {
      if (folderId === 'root') {
        countSql += ` AND folder_id IS NULL`;
      } else {
        countSql += ` AND folder_id = ?`;
        countParams.push(folderId);
      }
    }
    if (filterImportedKnowledge) {
      countSql += ` AND is_imported_knowledge = 1`;
    }

    const { total } = db.prepare(countSql).get(...countParams);

    const list = rows.map(r => ({
      id: r.id,
      title: r.title,
      materialType: r.material_type,
      source: r.source,
      channel: r.channel,
      folderId: r.folder_id,
      category: r.category,
      contentPreview: r.content_preview,
      wordCount: r.word_count,
      fileId: r.file_id,
      isImportedKnowledge: r.is_imported_knowledge === 1,
      createdAt: r.created_at
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

  // 2. GET /geekseek/aiwriter/document/v2/detail
  fastify.get('/geekseek/aiwriter/document/v2/detail', async (request, reply) => {
    const { docId, channel } = request.query;

    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    const row = db.prepare(`SELECT * FROM materials WHERE id = ?`).get(docId);
    if (!row) return reply.code(404).send({ code: 404, message: 'Material not found' });

    return {
      code: 200,
      message: 'success',
      data: {
        id: row.id,
        title: row.title,
        materialType: row.material_type,
        source: row.source,
        channel: row.channel,
        folderId: row.folder_id,
        category: row.category,
        contentPreview: row.content_preview,
        wordCount: row.word_count,
        fileId: row.file_id,
        isImportedKnowledge: row.is_imported_knowledge === 1,
        createdAt: row.created_at
      }
    };
  });

  // 3. POST /geekseek/aiwriter/document/v2/collect
  fastify.post('/geekseek/aiwriter/document/v2/collect', async (request, reply) => {
    const { docId, collect = true } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    // Mark as collected/imported knowledge
    db.prepare(`UPDATE materials SET is_imported_knowledge = ? WHERE id = ?`)
      .run(collect ? 1 : 0, docId);

    return { code: 200, message: 'success', data: true };
  });

  // 4. POST /geekseek/aiwriter/document/v2/delete
  fastify.post('/geekseek/aiwriter/document/v2/delete', async (request, reply) => {
    const { ids = [], channel } = request.body || {};
    if (!ids || ids.length === 0) return reply.code(400).send({ code: 400, message: 'ids are required' });

    // Permanent delete! Supports both document soft-deletes cleanup (v1) and materials delete (v2)
    const transaction = db.transaction((idList) => {
      const deleteMaterialStmt = db.prepare(`DELETE FROM materials WHERE id = ?`);
      const deleteDocStmt = db.prepare(`DELETE FROM documents WHERE id = ?`);

      for (const id of idList) {
        deleteMaterialStmt.run(id);
        deleteDocStmt.run(id);
      }
    });

    transaction(ids);

    return { code: 200, message: 'success', data: true };
  });

  // 5. POST /geekseek/aiwriter/document/v2/reParse
  fastify.post('/geekseek/aiwriter/document/v2/reParse', async (request, reply) => {
    return { code: 200, message: 'success', data: true };
  });

  // 6. POST /geekseek/aiwriter/document/v2/semanticSearch
  fastify.post('/geekseek/aiwriter/document/v2/semanticSearch', async (request, reply) => {
    const { query = '', limit = 5 } = request.body || {};

    // Fallback/Mock semantic search. Retrieve relevant materials matching keywords.
    let rows;
    if (query) {
      rows = db.prepare(`SELECT * FROM materials WHERE title LIKE ? OR content_preview LIKE ? LIMIT ?`)
        .all(`%${query}%`, `%${query}%`, limit);
    } else {
      rows = db.prepare(`SELECT * FROM materials LIMIT ?`).all(limit);
    }

    const list = rows.map(r => ({
      id: r.id,
      title: r.title,
      materialType: r.material_type,
      contentPreview: r.content_preview,
      wordCount: r.word_count
    }));

    return {
      code: 200,
      message: 'success',
      data: list
    };
  });

  // 7. GET /geekseek/aiwriter/document/v2/tag
  fastify.get('/geekseek/aiwriter/document/v2/tag', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: ['政策法规', '讲话参考', '工作计划', '总结提炼', '通知公告']
    };
  });

  // 8. POST /geekseek/aiwriter/document/v2/getKbImportStatus
  fastify.post('/geekseek/aiwriter/document/v2/getKbImportStatus', async (request, reply) => {
    return { code: 200, message: 'success', data: 'SUCCESS' };
  });

  // 9. POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus
  fastify.post('/geekseek/aiwriter/document/v2/getSmartLayoutStatus', async (request, reply) => {
    return { code: 200, message: 'success', data: { status: 'SUCCESS', progress: 100 } };
  });

  // 10. POST /geekseek/aiwriter/folder/v1/move
  fastify.post('/geekseek/aiwriter/folder/v1/move', async (request, reply) => {
    const { ids = [], folderId = null } = request.body || {};
    if (!ids || ids.length === 0) return reply.code(400).send({ code: 400, message: 'ids are required' });

    const finalFolderId = folderId === 'root' || folderId === '' ? null : folderId;

    const stmt = db.prepare(`UPDATE materials SET folder_id = ? WHERE id = ?`);
    const transaction = db.transaction((idList) => {
      for (const id of idList) {
        stmt.run(finalFolderId, id);
      }
    });

    transaction(ids);

    return { code: 200, message: 'success', data: true };
  });

  // 11. POST /geekseek/aiwriter/folder/v1/create
  fastify.post('/geekseek/aiwriter/folder/v1/create', async (request, reply) => {
    const { name, type = 'MATERIAL', parentId = null } = request.body || {};
    if (!name) return reply.code(400).send({ code: 400, message: 'name is required' });

    const newId = uuidv4();
    db.prepare(`
      INSERT INTO folders (id, name, type, parent_id, created_at)
      VALUES (?, ?, ?, ?, ?)
    `).run(newId, name, type, parentId, new Date().toISOString());

    return {
      code: 200,
      message: 'success',
      data: { id: newId, name, type, parentId }
    };
  });

  // 12. POST /geekseek/aiwriter/folder/v1/delete
  fastify.post('/geekseek/aiwriter/folder/v1/delete', async (request, reply) => {
    const { folderId } = request.body || {};
    if (!folderId) return reply.code(400).send({ code: 400, message: 'folderId is required' });

    // Move all materials in this folder back to root
    db.prepare(`UPDATE materials SET folder_id = NULL WHERE folder_id = ?`).run(folderId);
    // Delete folder
    db.prepare(`DELETE FROM folders WHERE id = ?`).run(folderId);

    return { code: 200, message: 'success', data: true };
  });

  // 13. POST /geekseek/aiwriter/folder/v1/list
  fastify.post('/geekseek/aiwriter/folder/v1/list', async (request, reply) => {
    const { type = 'MATERIAL' } = request.body || {};
    const rows = db.prepare(`SELECT * FROM folders WHERE type = ? ORDER BY created_at ASC`).all(type);

    const folders = rows.map(r => ({
      id: r.id,
      name: r.name,
      type: r.type,
      parentId: r.parent_id
    }));

    return {
      code: 200,
      message: 'success',
      data: folders
    };
  });
}
