export default async function userRoutes(fastify, options) {

  // 1. GET /gdios/api/user/getMyInfo
  fastify.get('/gdios/api/user/getMyInfo', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        userId: 'admin_user_001',
        username: '公文助理_小春',
        nickname: '小春',
        mobile: '13688880405',
        avatar: '',
        profession: '党政机关公文撰写员',
        role: 'ADMIN'
      }
    };
  });

  // 2. GET /gdios/api/setup/uiConfig
  fastify.get('/gdios/api/setup/uiConfig', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        title: '个知AI工作站 - 写作助手',
        version: '1.22.0',
        deploymentMode: 'SAAS',
        allowSmsLogin: true,
        allowPasswordLogin: true,
        showRegistration: true
      }
    };
  });

  // 3. GET /gdios/api/user/checkUserMsg
  fastify.get('/gdios/api/user/checkUserMsg', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        unreadCount: 0,
        messages: []
      }
    };
  });

  // 4. GET /gdios/api/user/getCurrentUserMenuList
  fastify.get('/gdios/api/user/getCurrentUserMenuList', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: [
        { id: '1', name: '创作中心', path: '/writer/document-list', icon: 'Document' },
        { id: '2', name: '素材文稿', path: '/writer/document-list/library', icon: 'Folder' },
        { id: '3', name: '智能排版', path: '/writer/document-list/typed', icon: 'Grid' },
        { id: '4', name: '文风模板', path: '/writer/document-list/style', icon: 'MagicStick' },
        { id: '5', name: '回收站', path: '/writer/document-list/dustbin', icon: 'Delete' }
      ]
    };
  });

  // 5. POST /gdios/api/service/userMembership/queryUsage
  fastify.post('/gdios/api/service/userMembership/queryUsage', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        totalTokens: 3000000,
        usedTokens: 31203,
        remainingTokens: 2968797,
        expireAt: '2027-12-31 23:59:59'
      }
    };
  });

  // 6. GET /geekseek/aiwriter/module/list
  fastify.get('/geekseek/aiwriter/module/list', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        writingAssistant: true,
        materialLibrary: true,
        smartLayout: true,
        styleTraining: true,
        proofreading: true,
        aiChat: true
      }
    };
  });

  // 7. GET /geekseek/aiwriter/common/getWritingConfig
  fastify.get('/geekseek/aiwriter/common/getWritingConfig', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        uploadMaxSizeMb: 10,
        allowedUploadFormats: ['doc', 'docx', 'txt', 'md', 'wps'],
        defaultSpeechWordCount: 3000,
        defaultNoticeWordCount: 1000
      }
    };
  });

  // 8. GET /geekseek/aiwriter/common/getUiConfig
  fastify.get('/geekseek/aiwriter/common/getUiConfig', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        primaryColor: '#5B6EF6',
        secondaryColor: '#7B5CF7',
        accentColor: '#4B6EE3',
        showWatermark: false
      }
    };
  });

  // 9. GET /geekseek/aiwriter/template/getWriterTemplateConfig
  fastify.get('/geekseek/aiwriter/template/getWriterTemplateConfig', async (request, reply) => {
    return {
      code: 200,
      message: 'success',
      data: {
        templatesEnabled: true,
        categories: [
          { code: 'SPEECH', name: '讲话稿' },
          { code: 'REFLECTION', name: '心得体会' },
          { code: 'WORK_REPORT', name: '工作报告' },
          { code: 'RESEARCH_REPORT', name: '调研报告' },
          { code: 'NOTICE', name: '通知' },
          { code: 'THANK_YOU_LETTER', name: '感谢信' }
        ]
      }
    };
  });
}
