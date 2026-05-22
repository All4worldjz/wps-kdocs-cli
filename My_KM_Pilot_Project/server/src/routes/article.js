import { v4 as uuidv4 } from 'uuid';
import db from '../database.js';

// Setup high-quality mock text templates for Chinese official documents in case LLM keys are absent
const MOCK_OUTLINES = {
  SPEECH: {
    title: '在推进数字政务协同办公工作会议上的讲话',
    nodes: [
      { id: '1', title: '一、提高政治站位，深刻认识数字政务建设的重大意义' },
      { id: '1.1', title: '1. 贯彻落实网络强国、数字中国战略部署' },
      { id: '1.2', title: '2. 数字化转型是提升政府治理效能的必然选择' },
      { id: '2', title: '二、聚焦核心任务，高质量推进协同办公平台建设' },
      { id: '2.1', title: '1. 打破数据壁垒，实现跨层级、跨部门数据共享' },
      { id: '2.2', title: '2. 创新服务模式，提供全场景智能办文办会服务' },
      { id: '3', title: '三、强化安全保障，筑牢数字政务运行安全底线' },
      { id: '3.1', title: '1. 严格落实网络安全等级保护与合规要求' },
      { id: '3.2', title: '2. 强化国产密码应用与数据全生命周期防护' },
      { id: '4', title: '四、完善组织实施，确保各项任务落到实处' }
    ]
  },
  REFLECTION: {
    title: '关于深入学习贯彻数字化改革重要论述的心得体会',
    nodes: [
      { id: '1', title: '一、深学细悟，感悟数字化改革的真理力量和实践伟力' },
      { id: '2', title: '二、对标对表，清醒认识工作中存在的差距和短板' },
      { id: '3', title: '三、笃行实干，以数字化改革赋能高质量发展新篇章' }
    ]
  },
  DEFAULT: {
    title: '关于数字化转型工作的方案提纲',
    nodes: [
      { id: '1', title: '一、指导思想与总体目标' },
      { id: '2', title: '二、主要任务与关键节点' },
      { id: '3', title: '三、保障措施与考核机制' }
    ]
  }
};

const MOCK_ARTICLES = {
  SPEECH: `
    <h2>在推进数字政务协同办公工作会议上的讲话</h2>
    <p>同志们：</p>
    <p>今天，我们召开这次专题工作会议，主要任务是深入学习贯彻落实国家关于加强数字政府建设的战略部署，总结交流前期工作经验，动员部署下一阶段数字政务与智能化协同办公平台建设的核心任务。下面，我讲三点意见。</p>
    <h3>一、提高政治站位，深刻认识数字政务建设的重大意义</h3>
    <p>加强数字政府和数字政务建设，是推进国家治理体系和治理能力现代化的重要举措。我们要充分认识到，数字化转型不仅是技术手段的革新，更是一场深刻的治理变革。通过智能协同办公系统的应用，能够极大缩短办文办会周期，促进跨部门的高效协同，让政务运转更加灵敏、透明、高效。</p>
    <h3>二、聚焦核心任务，高质量推进协同办公平台建设</h3>
    <p>在接下来的推进过程中，我们要重点做好“打通数据壁垒”和“创新智能应用”两篇文章。要坚持“全省一盘棋、全国一体化”的系统思维，推动跨层级、跨地域的互联互通。同时，要积极引入AI写作辅助、智能校对等创新工具，把公文撰写员从繁琐的机械排版中解放出来，聚焦核心政策的研究与贯彻。</p>
    <h3>三、强化安全保障，筑牢数字政务运行安全底线</h3>
    <p>安全是数字政务的生命线。我们必须时刻绷紧安全这根弦。要严格落实网络安全防护，保障国产密码技术在办文流转中的深层次应用，确保机密数据不出网、敏感信息不泄露。以防御性、可控性的安全架构，为数字化改革保驾护航！</p>
    <p>同志们，数字政府建设时间紧、任务重。让我们凝心聚力，砥砺奋进，共同谱写数字化政务的高质量协同新篇章！谢谢大家。</p>
  `,
  NOTICE: `
    <h2>关于推进数字化转型与智能写作助手应用测试的通知</h2>
    <p>各部、委、办、局，各企事业单位：</p>
    <p>为贯彻落实办公厅数字化改革总体规划，进一步提升机关事务处理效能与办文效率，经研究决定，即日起在全区范围内开展“个知AI写作助手”的部署与试用工作。现将有关事项通知如下：</p>
    <p><strong>一、试用范围与核心场景</strong><br>
    本次试用主要针对日常讲话稿、心得体会、通知、工作总结等常见公文场景。重点测试AI交互式写作向导、智能排版以及公文纠错校对等功能模块。</p>
    <p><strong>二、操作流程与节点要求</strong><br>
    1. 各单位文秘人员需登录平台并完成实名注册；<br>
    2. 上传各部门典型公文素材进行本地化“文风训练”；<br>
    3. 在撰写相关材料时，积极应用智能排版功能确保格式合规。</p>
    <p><strong>三、信息保障与机密防护</strong><br>
    试用期间，各单位须严格遵守保密守则，严禁上传包含绝密、机密级国家秘密的材料。所有测试文稿应做脱敏处理，确保信息安全流转。</p>
    <p>特此通知。</p>
    <p style="text-align: right;">数字化工作领导小组办公室<br>2026年5月22日</p>
  `,
  DEFAULT: `
    <h2>数字化转型工作阶段性方案</h2>
    <p>随着数字化时代的全面铺开，各项业务的集约化、系统化管理迫在眉睫。本方案致力于打通现存业务阻碍，通过智能化系统的全面嵌入，实现效率的跨越式跃升。</p>
    <p>一是确立核心目标，力争在半年内实现日常报表、文字审批的100%线上无纸化流转。二是构建安全堡垒，运用本地沙箱、Bearer-Token认证等机制确保审计留痕。三是强化人员内训，确保每位核心干事均能娴熟调遣AI助手，实现减负增效。</p>
  `
};

export default async function articleRoutes(fastify, options) {

  // 1. POST /geekseek/aiwriter/article/v1/getExplainContent
  fastify.post('/geekseek/aiwriter/article/v1/getExplainContent', async (request, reply) => {
    const { explain = '', category = 'SPEECH' } = request.body || {};

    // Quick summarize concept
    const summary = explain
      ? `本文档根据交代内容“${explain}”进行构思，旨在建立一篇围绕该主题的结构严密、语调得体、逻辑清晰的${category === 'SPEECH' ? '正式讲话材料' : '公文文稿'}。`
      : `本文档为一篇围绕数字化改革与智能写作提效而撰写的${category === 'SPEECH' ? '正式讲话材料' : '公文文稿'}。`;

    return {
      code: 200,
      message: 'success',
      data: summary
    };
  });

  // 2. POST /geekseek/aiwriter/article/v1/checkSensitiveWord
  fastify.post('/geekseek/aiwriter/article/v1/checkSensitiveWord', async (request, reply) => {
    const { text = '' } = request.body || {};
    // Return empty list indicating safe, unless user inputs specific flagged words
    const matches = [];
    if (text.includes('反动') || text.includes('机密泄漏')) {
      matches.push({ word: '反动', type: 'POLITICAL_SENSITIVE', advice: '请替换为客观中性词汇' });
    }
    return {
      code: 200,
      message: 'success',
      data: matches
    };
  });

  // 3. POST /geekseek/aiwriter/article/v1/checkOutlineSensitiveWord
  fastify.post('/geekseek/aiwriter/article/v1/checkOutlineSensitiveWord', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: []
    };
  });

  // 4. POST /geekseek/aiwriter/article/v1/generateExplainQrCode
  fastify.post('/geekseek/aiwriter/article/v1/generateExplainQrCode', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        qrCodeUrl: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="%23f5f7ff"/><text x="10" y="50" font-family="sans-serif" font-size="10" fill="%235b6ef6">扫码交代语音</text></svg>'
      }
    };
  });

  // 5. POST /geekseek/aiwriter/article/v1/outlineOrTitle/generateStream (SSE)
  fastify.post('/geekseek/aiwriter/article/v1/outlineOrTitle/generateStream', async (request, reply) => {
    const {
      category = 'SPEECH',
      explain = '',
      references = []
    } = request.body || {};

    const outlineData = MOCK_OUTLINES[category] || MOCK_OUTLINES.DEFAULT;

    // Set SSE headers
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no'
    });

    // We stream the title and outline items
    const streamPayload = {
      title: outlineData.title,
      nodes: outlineData.nodes
    };

    // Serialize payload and chunk stream to simulate AI generation
    const jsonStr = JSON.stringify(streamPayload);
    const chunkSize = 15;
    let index = 0;

    const interval = setInterval(() => {
      if (index >= jsonStr.length) {
        reply.raw.write(`data: [DONE]\n\n`);
        clearInterval(interval);
        reply.raw.end();
        return;
      }

      const chunk = jsonStr.slice(index, index + chunkSize);
      index += chunkSize;

      // SSE formatting
      reply.raw.write(`data: ${chunk}\n\n`);
    }, 40);

    // Handle client disconnect
    request.raw.on('close', () => {
      clearInterval(interval);
    });
  });

  // 6. POST /geekseek/aiwriter/article/v1/generate (SSE)
  fastify.post('/geekseek/aiwriter/article/v1/generate', async (request, reply) => {
    const {
      docId,
      category = 'SPEECH',
      title = '新创作文稿',
      explain = '',
      outline = []
    } = request.body || {};

    const textToStream = MOCK_ARTICLES[category] || MOCK_ARTICLES.DEFAULT;

    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no'
    });

    let index = 0;
    const chunkSize = 25; // Stream faster for better user experience

    const interval = setInterval(() => {
      if (index >= textToStream.length) {
        // SSE generation completed. Let's persist to database as finished text if docId is provided
        if (docId) {
          try {
            const now = new Date().toISOString();
            const textContentOnly = textToStream.replace(/<[^>]*>/g, ''); // strip HTML tags

            // Check if document exists
            const doc = db.prepare(`SELECT * FROM documents WHERE id = ?`).get(docId);
            if (doc) {
              db.prepare(`
                UPDATE documents
                SET title = ?, content_html = ?, content_text = ?, word_count = ?, updated_at = ?
                WHERE id = ?
              `).run(title, textToStream, textContentOnly, textContentOnly.length, now, docId);
            } else {
              db.prepare(`
                INSERT INTO documents (id, title, content_html, content_text, category, word_count, is_imported_knowledge, parse_status, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 'SUCCESS', 1, ?, ?)
              `).run(docId, title, textToStream, textContentOnly, category, textContentOnly.length, now, now);
            }
          } catch (err) {
            console.error('Persist on stream complete failed:', err);
          }
        }

        reply.raw.write(`data: [DONE]\n\n`);
        clearInterval(interval);
        reply.raw.end();
        return;
      }

      const chunk = textToStream.slice(index, index + chunkSize);
      index += chunkSize;

      reply.raw.write(`data: ${chunk}\n\n`);
    }, 30);

    request.raw.on('close', () => {
      clearInterval(interval);
    });
  });

  // 7. POST /geekseek/aiwriter/article/v1/optimize
  fastify.post('/geekseek/aiwriter/article/v1/optimize', async (request, reply) => {
    const {
      text = '',
      type = 'POLISH' // POLISH | EXPAND | SHORTEN | REWRITE
    } = request.body || {};

    let result = '';
    if (type === 'POLISH') {
      result = `【润色结果】 ${text}。同时对行文语句进行了精炼提纯，加强了字里行间的逻辑衔接，更符合党政公文稳重、凝练的语态规格。`;
    } else if (type === 'EXPAND') {
      result = `【扩写结果】 ${text}。在此基础上我们需要坚持创新引领，从体制机制建设到具体落地实施双管齐下，紧密结合各下属工作单元，扎实推进战略共识，构建长期、健康的业务增长韧性体系。`;
    } else if (type === 'SHORTEN') {
      result = `【缩写结果】 针对以下要点进行了合并精简：${text.slice(0, 50)}...（要旨在于落实数字化核心指标，确保平稳过渡）。`;
    } else {
      result = `【改写结果】 【重构表述】：关于“${text}”，我们在具体实施层面上需要采用更加集约化、跨部门并进的工作模式，以全面激发协同能效。`;
    }

    return {
      code: 200,
      message: 'success',
      data: result
    };
  });

  // 8. POST /geekseek/aiwriter/article/v1/citationSource
  fastify.post('/geekseek/aiwriter/article/v1/citationSource', async (request, reply) => {
    const { docId } = request.body || {};
    return {
      code: 200,
      message: 'success',
      data: [
        { id: 'ref_01', title: '党政协同公文规范手册（2025年版）', index: 1 }
      ]
    };
  });

  // 9. POST /geekseek/aiwriter/article/v1/md2Html
  fastify.post('/geekseek/aiwriter/article/v1/md2Html', async (request, reply) => {
    const { markdown = '' } = request.body || {};
    // Very simple mock converter
    const html = `<p>${markdown.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;
    return {
      code: 200,
      message: 'success',
      data: html
    };
  });
}
