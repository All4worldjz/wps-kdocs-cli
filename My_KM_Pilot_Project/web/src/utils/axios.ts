import axios from 'axios';
import { ElMessage } from 'element-plus';

const instance = axios.create({
  baseURL: '', // Same domain proxy is used via Vite
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Geekseek-Language': 'zh-CN'
  }
});

// Request interceptor to automatically attach authorization header
instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('GEEKSEEK_USER_TOKEN') || 'mock_token_xiaochun_2026';
    config.headers['Geekseek-Authorization'] = token;
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle standard API envelopes
instance.interceptors.response.use(
  (response) => {
    const res = response.data;
    if (res && res.code !== 200) {
      ElMessage.error(res.message || '操作失败');
      return Promise.reject(new Error(res.message || 'Error'));
    }
    return res;
  },
  (error) => {
    console.error('API Error:', error);
    ElMessage.error(error.message || '网络连接故障，请检查后端服务是否启动');
    return Promise.reject(error);
  }
);

export default instance;
