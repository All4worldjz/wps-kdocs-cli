import db from '../database.js';
import { v4 as uuidv4 } from 'uuid';

const MOCK_FORMAT_TEMPLATES = [
  { id: 'layout_template_01', name: '通用格式-无红头', group: 'UNIVERSAL', desc: '标准的政企公文通用格式，不包含红头。' },
  { id: 'layout_template_02', name: '通用格式-有红头', group: 'UNIVERSAL', desc: '标准的政企公文通用格式，自带红头背景。' },
  { id: 'layout_template_03', name: '报告', group: 'LEGAL', desc: '适用于向上级机关汇报工作、反映情况等。' },
  { id: 'layout_template_04', name: '公报', group: 'LEGAL', desc: '适用于公布重要决定或者重大事项。' },
  { id: 'layout_template_05', name: '公告', group: 'LEGAL', desc: '适用于向国内外宣布重要事项或者法定事项。' },
  { id: 'layout_template_06', name: '函', group: 'LEGAL', desc: '适用于不相隶属机关之间商洽工作、询问和答复问题。' },
  { id: 'layout_template_07', name: '纪要', group: 'LEGAL', desc: '适用于记载会议主要情况和议定事项。' },
  { id: 'layout_template_08', name: '决定', group: 'LEGAL', desc: '适用于对重要事项作出决策和部署。' },
  { id: 'layout_template_09', name: '决议', group: 'LEGAL', desc: '适用于会议讨论通过的重大决策事项。' },
  { id: 'layout_template_10', name: '令（命令）', group: 'LEGAL', desc: '适用于公布行政法规和规章、宣布施行重大强制性措施。' },
  { id: 'layout_template_11', name: '批复', group: 'LEGAL', desc: '适用于答复下级机关的请示事项。' },
  { id: 'layout_template_12', name: '请示', group: 'LEGAL', desc: '适用于向上级机关请求指示、批准。' },
  { id: 'layout_template_13', name: '通报', group: 'LEGAL', desc: '适用于表彰先进、批评错误、传达重要精神。' },
  { id: 'layout_template_14', name: '通告', group: 'LEGAL', desc: '适用于在一定范围内公布应当遵守或者周知的事项。' },
  { id: 'layout_template_15', name: '通知', group: 'LEGAL', desc: '适用于发布、传达要求下级机关执行和有关单位周知的事项。' },
  { id: 'layout_template_16', name: '议案', group: 'LEGAL', desc: '适用于各级人民政府按照法律程序向同级人大提交的议案。' },
  { id: 'layout_template_17', name: '意见', group: 'LEGAL', desc: '适用于对重要问题提出见解和处理办法。' }
];

export default async function layoutAndTasksRoutes(fastify, options) {

  // 1. POST /geekseek/aiwriter/format/template/list
  fastify.post('/geekseek/aiwriter/format/template/list', async (request, reply) => {
    const { group = 'ALL' } = request.body || {};
    let templates = MOCK_FORMAT_TEMPLATES;
    if (group !== 'ALL') {
      templates = MOCK_FORMAT_TEMPLATES.filter(t => t.group === group);
    }
    return {
      code: 200,
      message: 'success',
      data: templates
    };
  });

  // 2. GET /geekseek/aiwriter/format/template/group/list
  fastify.get('/geekseek/aiwriter/format/template/group/list', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: [
        { code: 'ALL', name: '全部格式' },
        { code: 'UNIVERSAL', name: '通用格式' },
        { code: 'LEGAL', name: '法定公文' },
        { code: 'CUSTOM', name: '自定格式' }
      ]
    };
  });

  // 3. POST /geekseek/aiwriter/file/v2/upload (Mock Upload File)
  fastify.post('/geekseek/aiwriter/file/v2/upload', async (request, reply) => {
    // Standard file upload mock. Returns simulated file id and saves to materials table.
    const mockFileId = `file_${uuidv4().slice(0, 8)}`;
    const mockTitle = 'gai_cn_safe_upload_test.txt';
    const now = new Date().toISOString();

    // Add to materials PERSONAL_MATERIAL channel
    const matId = uuidv4();
    db.prepare(`
      INSERT INTO materials (id, title, material_type, source, channel, category, content_preview, word_count, file_id, is_imported_knowledge, created_at)
      VALUES (?, ?, 'PERSONAL_MATERIAL', '自主上传', 'PERSONAL_MATERIAL', '其他', '本文件为安全测试上传样本。个知AI工作站包含写作助手、素材文稿、智能排版、文风模板与回收站。主要用于公文撰写和知识管理。', 155, ?, 0, ?)
    `).run(matId, mockTitle, mockFileId, now);

    return {
      code: 200,
      message: 'success',
      data: {
        fileId: mockFileId,
        fileName: mockTitle,
        size: 524,
        url: `/geekseek/aiwriter/file/storage/v1/download?fileId=${mockFileId}`
      }
    };
  });

  // 4. POST /geekseek/aiwriter/smart/layout/v2/upload (Create Smart Layout Task)
  fastify.post('/geekseek/aiwriter/smart/layout/v2/upload', async (request, reply) => {
    const mockFileId = `file_${uuidv4().slice(0, 8)}`;
    const mockTitle = 'gai_cn_safe_upload_test_排版.docx';
    const taskId = uuidv4();
    const now = new Date().toISOString();

    // Create a background layout task
    db.prepare(`
      INSERT INTO smart_layouts (id, source_file_id, template_id, title, status, output_doc_id, word_count, created_at, updated_at)
      VALUES (?, ?, 'layout_template_01', ?, 'SUCCESS', ?, 155, ?, ?)
    `).run(taskId, mockFileId, mockTitle, mockFileId, now, now);

    return {
      code: 200,
      message: 'success',
      data: {
        taskUuid: taskId,
        fileName: mockTitle,
        fileId: mockFileId
      }
    };
  });

  // 5. POST /geekseek/aiwriter/file/v1/createDownloadFileTask (Create Word/PDF export task)
  fastify.post('/geekseek/aiwriter/file/v1/createDownloadFileTask', async (request, reply) => {
    const { docId, exportType = 'docx' } = request.body || {};
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    const doc = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(docId);
    if (!doc) return reply.code(404).send({ code: 404, message: 'Document not found' });

    const taskUuid = uuidv4();
    const now = new Date().toISOString();

    db.prepare(`
      INSERT INTO async_tasks (id, type, subject_id, status, progress, input_json, output_json, error_message, created_at, updated_at)
      VALUES (?, ?, ?, 'PENDING', 0, ?, ?, NULL, ?, ?)
    `).run(
      taskUuid,
      exportType === 'pdf' ? 'EXPORT_PDF' : 'EXPORT_WORD',
      docId,
      JSON.stringify({ docId, exportType }),
      JSON.stringify({ taskUuid, downloadUrl: `/geekseek/aiwriter/file/v2/download?taskUuid=${taskUuid}` }),
      now,
      now
    );

    return {
      code: 200,
      message: 'success',
      data: {
        taskUuid
      }
    };
  });

  // 6. POST /geekseek/aiwriter/file/v1/taskStatus (Async tasks polling status)
  fastify.post('/geekseek/aiwriter/file/v1/taskStatus', async (request, reply) => {
    const { taskUuid } = request.body || {};
    if (!taskUuid) return reply.code(400).send({ code: 400, message: 'taskUuid is required' });

    const r = db.prepare(`SELECT * FROM async_tasks WHERE id = ?`).get(taskUuid);
    if (!r) return reply.code(404).send({ code: 404, message: 'Task not found' });

    let progress = r.progress;
    let status = r.status;

    if (r.status === 'PENDING') {
      progress = 50;
      status = 'PROCESSING';
      db.prepare(`UPDATE async_tasks SET progress = 50, status = 'PROCESSING', updated_at = ? WHERE id = ?`)
        .run(new Date().toISOString(), taskUuid);
    } else if (r.status === 'PROCESSING') {
      progress = 100;
      status = 'SUCCESS';
      db.prepare(`UPDATE async_tasks SET progress = 100, status = 'SUCCESS', updated_at = ? WHERE id = ?`)
        .run(new Date().toISOString(), taskUuid);
    }

    return {
      code: 200,
      message: 'success',
      data: {
        taskUuid: r.id,
        status,
        progress,
        resultUrl: status === 'SUCCESS' ? `/geekseek/aiwriter/file/v2/download?taskUuid=${r.id}` : null
      }
    };
  });

  // 7. GET /geekseek/aiwriter/file/v2/download (Exported file download blob)
  fastify.get('/geekseek/aiwriter/file/v2/download', async (request, reply) => {
    const { taskUuid } = request.query;
    if (!taskUuid) return reply.code(400).send({ code: 400, message: 'taskUuid is required' });

    const r = db.prepare(`SELECT * FROM async_tasks WHERE id = ?`).get(taskUuid);
    if (!r) return reply.code(404).send({ code: 404, message: 'Task not found' });

    // Output simulated Word document binary
    reply.header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    reply.header('Content-Disposition', `attachment; filename=gai_cn_export_${taskUuid.slice(0, 8)}.docx`);

    // Send standard 200 bytes mock buffer
    const mockBuffer = Buffer.alloc(1024, 'GAI_EXPORT_DOCX_MOCK_DATA');
    return reply.send(mockBuffer);
  });

  // 8. GET /geekseek/aiwriter/file/v1/download (Direct document download blob)
  fastify.get('/geekseek/aiwriter/file/v1/download', async (request, reply) => {
    const { docId } = request.query;
    if (!docId) return reply.code(400).send({ code: 400, message: 'docId is required' });

    reply.header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    reply.header('Content-Disposition', `attachment; filename=gai_cn_direct_export_${docId.slice(0, 8)}.docx`);
    const mockBuffer = Buffer.alloc(1024, 'GAI_DIRECT_DOCX_MOCK_DATA');
    return reply.send(mockBuffer);
  });
}
