import { createRouter, createWebHistory } from 'vue-router';
import Layout from '../views/Layout.vue';

const routes = [
  {
    path: '/',
    redirect: '/writer'
  },
  {
    path: '/writer',
    component: Layout,
    redirect: '/writer/document-list',
    children: [
      {
        path: 'document-list',
        name: 'DocumentList',
        component: () => import('../views/List.vue')
      },
      {
        path: 'document-list/library',
        name: 'Library',
        component: () => import('../views/Library.vue')
      },
      {
        path: 'document-list/typed',
        name: 'Typed',
        component: () => import('../views/Typed.vue')
      },
      {
        path: 'document-list/style',
        name: 'Style',
        component: () => import('../views/Style.vue')
      },
      {
        path: 'document-list/dustbin',
        name: 'Dustbin',
        component: () => import('../views/Dustbin.vue')
      }
    ]
  },
  {
    path: '/writer/content/create',
    name: 'CreateDocument',
    component: () => import('../views/Editor.vue')
  },
  {
    path: '/writer/edit/:docId',
    name: 'EditDocumentLegacy',
    component: () => import('../views/Editor.vue')
  },
  {
    path: '/writer/content/edit/:docId',
    name: 'EditDocument',
    component: () => import('../views/Editor.vue')
  },
  {
    path: '/writer/content/chat/:docId',
    name: 'ChatDocument',
    component: () => import('../views/Chat.vue')
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

export default router;
